from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from app.agent.agent import OperationsAgent
from app.workflows import store
from app.workflows.models import AgentRun, Workflow, WorkflowStep, utc_now


READ_ONLY_ACTIONS = {"get_tasks", "get_reminders"}
UNFULFILLED_MARKERS = (
    "not found", "could not", "couldn't", "unable to", "cannot",
    "can't", "failed to", "wasn't able", "were not able",
)


def _resource_refs(observation: Dict[str, Any]) -> List[str]:
    payload = observation.get("result")
    if not isinstance(payload, dict):
        return []
    refs = []
    for key in ("task", "reminder", "event", "draft", "email"):
        item = payload.get(key)
        if isinstance(item, dict) and item.get("id") is not None:
            refs.append(str(item["id"]))
    events = payload.get("events")
    if isinstance(events, list):
        refs.extend(str(item["id"]) for item in events if isinstance(item, dict) and item.get("id") is not None)
    return refs


def _has_unfulfilled_message(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in UNFULFILLED_MARKERS)


def _snapshot(workflow: Workflow, run: AgentRun) -> Dict[str, Any]:
    return {
        "workflow": workflow,
        "run": run,
        "steps": store.get_steps(run),
    }


def execute_workflow(objective: str, agent: OperationsAgent) -> Dict[str, Any]:
    objective = objective.strip()
    workflow = store.create_workflow(title=objective, objective=objective)
    run = store.create_run(workflow)

    def record_step(
        order: int,
        decision: Any,
        arguments: Dict[str, Any],
        observation: Dict[str, Any],
        started_at: datetime,
    ) -> None:
        ok = bool(observation.get("success", False))
        error = observation.get("error")
        if error is None and not ok:
            inner = observation.get("result")
            if isinstance(inner, dict):
                error = inner.get("error")
        inner_result = observation.get("result")
        returned_title = None
        if isinstance(inner_result, dict):
            for resource in ("task", "reminder"):
                item = inner_result.get(resource)
                if isinstance(item, dict) and item.get("title"):
                    returned_title = item["title"]
                    break
        title = (
            getattr(decision, "title", None)
            or returned_title
            or decision.action.replace("_", " ").capitalize()
        )
        step = WorkflowStep(
            id=str(uuid4()),
            workflow_id=workflow.id,
            run_id=run.id,
            order=order,
            title=title,
            action=decision.action,
            arguments=arguments,
            status="completed" if ok else "failed",
            started_at=started_at,
            finished_at=utc_now(),
            result=observation,
            error=error,
            resource_refs=_resource_refs(observation),
        )
        store.add_step(step)

    try:
        agent_result = agent.run(
            objective,
            step_callback=record_step,
            context_exclude_workflow_id=workflow.id,
        )
        run.final_message = agent_result.get("final_message")
        steps = store.get_steps(run)
        successful_work = any(
            step.status == "completed" and step.action not in READ_ONLY_ACTIONS
            for step in steps
        )
        failed_step = any(step.status == "failed" for step in steps)
        unfulfilled = _has_unfulfilled_message(run.final_message or "")
        succeeded = bool(agent_result.get("success")) and not failed_step and not unfulfilled
        if succeeded:
            status = "completed"
        elif successful_work:
            status = "partially_completed"
        else:
            status = "failed"
        agent_result["success"] = succeeded
        run.status = status
        workflow.status = status
        return {**_snapshot(workflow, run), "agent_result": agent_result}
    except Exception as exc:
        steps = store.get_steps(run)
        successful_work = any(
            step.status == "completed" and step.action not in READ_ONLY_ACTIONS
            for step in steps
        )
        run.status = "partially_completed" if successful_work else "failed"
        workflow.status = run.status
        run.final_message = str(exc)
        return {**_snapshot(workflow, run), "agent_result": {
            "success": False,
            "instruction": objective,
            "steps": [],
            "final_message": str(exc),
        }}
    finally:
        run.finished_at = utc_now()
        workflow.active_run_id = None
        workflow.updated_at = utc_now()


def execute_approved_plan(
    objective: str,
    approval_id: str,
    actions: List[Any],
    controller: Any,
    validate_action: Any,
) -> Dict[str, Any]:
    """Execute an already-approved fixed plan and record its workflow history.

    Planning and validation remain outside WorkflowService. The supplied
    callback rechecks approval preconditions immediately before each action;
    all tool execution still passes through AgentController.
    """
    objective = objective.strip()
    workflow = store.create_workflow(
        title=objective,
        objective=objective,
        source_approval_id=approval_id,
    )
    run = store.create_run(workflow)
    steps: List[WorkflowStep] = []
    successful_work = False
    stop_reason: str | None = None

    for index, action in enumerate(actions):
        started_at = utc_now()
        error = validate_action(action)
        status = "stale" if error else "failed"
        result = None

        if error is None:
            try:
                execution = controller.execute_plan([{
                    "tool": action.action,
                    "arguments": action.arguments,
                    "approval_id": approval_id,
                    "approval_action_id": action.id,
                }])
                result = execution["results"][0]["result"]
                succeeded = bool(result.get("success", False))
                status = "completed" if succeeded else "failed"
                if not succeeded:
                    inner = result.get("result")
                    error = (
                        result.get("error")
                        or (inner.get("error") if isinstance(inner, dict) else None)
                        or "Tool execution failed."
                    )
                else:
                    successful_work = True
            except Exception as exc:
                status = "failed"
                error = str(exc) or exc.__class__.__name__

        if status in {"failed", "stale"}:
            stop_reason = error or ("Action became stale." if status == "stale" else "Tool execution failed.")

        step = WorkflowStep(
            id=str(uuid4()),
            workflow_id=workflow.id,
            run_id=run.id,
            order=index + 1,
            title=(
                action.arguments.get("title")
                or f"{action.action.replace('_', ' ').capitalize()}"
            ),
            action=action.action,
            arguments=dict(action.arguments),
            status=status,
            started_at=started_at,
            finished_at=utc_now(),
            result=result,
            error=error,
            resource_refs=_resource_refs(result) if isinstance(result, dict) else [],
            approval_action_id=action.id,
        )
        store.add_step(step)
        steps.append(step)
        action.status = status
        action.result = result
        action.error = error
        action.resource_refs = list(step.resource_refs)

        if status in {"failed", "stale"}:
            skipped_reason = (
                "Not executed after an earlier action became stale."
                if status == "stale"
                else "Not executed after an earlier action failed."
            )
            for skipped_index, skipped_action in enumerate(actions[index + 1:], start=index + 2):
                skipped = WorkflowStep(
                    id=str(uuid4()),
                    workflow_id=workflow.id,
                    run_id=run.id,
                    order=skipped_index,
                    title=(skipped_action.arguments.get("title") or skipped_action.action.replace("_", " ").capitalize()),
                    action=skipped_action.action,
                    arguments=dict(skipped_action.arguments),
                    status="skipped",
                    started_at=utc_now(),
                    finished_at=utc_now(),
                    error=skipped_reason,
                    approval_action_id=skipped_action.id,
                )
                store.add_step(skipped)
                steps.append(skipped)
                skipped_action.status = "skipped"
                skipped_action.error = skipped_reason
            break

    has_failure = any(step.status in {"failed", "stale", "skipped"} for step in steps)
    if not has_failure:
        status = "completed"
        run.final_message = "All approved actions completed successfully."
    elif successful_work:
        status = "partially_completed"
        run.final_message = f"Some approved actions completed, then execution stopped: {stop_reason}"
    else:
        status = "failed"
        run.final_message = f"No approved actions completed. Execution stopped: {stop_reason}"

    run.status = status
    workflow.status = status
    run.finished_at = utc_now()
    workflow.active_run_id = None
    workflow.updated_at = utc_now()
    return {**_snapshot(workflow, run), "final_message": run.final_message}


def get_workflow_detail(workflow: Workflow) -> Dict[str, Any]:
    runs = []
    for run_id in workflow.run_ids:
        run = store.get_run(run_id)
        if run is not None:
            runs.append({"run": run, "steps": store.get_steps(run)})
    return {"workflow": workflow, "runs": runs}
