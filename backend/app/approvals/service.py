import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.agent.workspace_context import get_workspace_context
from app.approvals import store
from app.approvals.models import ApprovalRequest, ProposedAction, utc_now
from app.workflows.service import execute_approved_plan


class ApprovalServiceError(Exception):
    status_code = 400


class ApprovalNotFound(ApprovalServiceError):
    status_code = 404


class InvalidProposal(ApprovalServiceError):
    status_code = 422


class InvalidApprovalState(ApprovalServiceError):
    status_code = 409


_state_lock = threading.RLock()
_PROPOSED_ACTIONS = {
    "create_task",
    "complete_task",
    "update_task",
    "create_reminder",
    "create_calendar_event",
    "get_calendar_events",
    "update_calendar_event",
    "cancel_calendar_event",
    "draft_email",
    "send_email",
}


def _normalized_title(title: str) -> str:
    return " ".join(title.split()).casefold()


def _ensure_like(objective: str) -> bool:
    explicit_creation = re.search(
        r"\b(?:create|add)\b.*\btask\b|\bmake\s+(?:me\s+)?(?:another|a|one|new)\s+task\b",
        objective,
        re.IGNORECASE,
    )
    return bool(
        re.search(r"\b(?:ensure|prepare|check|verify|confirm)\b|\bmake\s+sure\b", objective, re.I)
        and not explicit_creation
    )


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidProposal(f"{name} must be a positive integer.")
    return value


def _iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _validate_arguments(action: str, value: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidProposal("Action arguments must be an object.")

    schemas = {
        "create_task": ({"title", "description"}, {"title"}),
        "complete_task": ({"task_id"}, {"task_id"}),
        "update_task": ({"task_id", "title", "description"}, {"task_id"}),
        "create_reminder": ({"title", "reminder_time"}, {"title", "reminder_time"}),
        "create_calendar_event": (
            {"title", "start_time", "end_time", "description", "timezone", "location"},
            {"title", "start_time", "end_time"},
        ),
        "get_calendar_events": ({"start_time", "end_time"}, set()),
        "update_calendar_event": (
            {"event_id", "title", "start_time", "end_time", "description", "timezone", "location"},
            {"event_id"},
        ),
        "cancel_calendar_event": ({"event_id"}, {"event_id"}),
        "draft_email": ({"to", "cc", "subject", "body"}, {"to", "subject", "body"}),
        "send_email": ({"to", "cc", "subject", "body"}, {"to", "subject", "body"}),
    }
    allowed, required = schemas[action]
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise InvalidProposal(f"Unsupported arguments for {action}: {', '.join(sorted(unknown))}.")
    if missing:
        raise InvalidProposal(f"Missing required arguments for {action}: {', '.join(sorted(missing))}.")

    arguments = dict(value)
    if action in {"create_task", "create_reminder", "create_calendar_event"}:
        if not isinstance(arguments["title"], str) or not arguments["title"].strip():
            raise InvalidProposal("Action title must be a non-empty string.")
        arguments["title"] = arguments["title"].strip()
    if "description" in arguments and not isinstance(arguments["description"], str):
        raise InvalidProposal("Task description must be a string.")
    if "task_id" in arguments:
        arguments["task_id"] = _integer(arguments["task_id"], "task_id")
    if action == "update_task":
        if not any(key in arguments for key in ("title", "description")):
            raise InvalidProposal("update_task must include a title or description change.")
        if "title" in arguments and (not isinstance(arguments["title"], str) or not arguments["title"].strip()):
            raise InvalidProposal("Updated task title must be a non-empty string.")
        task = next((item for item in context["tasks"] if item.get("id") == arguments["task_id"]), None)
        if task is None:
            raise InvalidProposal(f"Task {arguments['task_id']} does not exist.")
    if action == "complete_task":
        task = next((item for item in context["tasks"] if item.get("id") == arguments["task_id"]), None)
        if task is None or task.get("status") != "pending":
            raise InvalidProposal("complete_task must reference an existing pending task.")
    if action == "create_reminder":
        if not isinstance(arguments["reminder_time"], str):
            raise InvalidProposal("reminder_time must use YYYY-MM-DD HH:MM format.")
        try:
            datetime.strptime(arguments["reminder_time"], "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise InvalidProposal("reminder_time must use YYYY-MM-DD HH:MM format.") from exc
    if action in {"create_calendar_event", "get_calendar_events", "update_calendar_event"}:
        for field in ("start_time", "end_time"):
            if field not in arguments:
                continue
            if not isinstance(arguments[field], str):
                raise InvalidProposal(f"{field} must be an ISO 8601 date-time string.")
            try:
                _iso_datetime(arguments[field])
            except ValueError as exc:
                raise InvalidProposal(f"{field} must be an ISO 8601 date-time string.") from exc
        if "start_time" in arguments and "end_time" in arguments:
            start = _iso_datetime(arguments["start_time"])
            end = _iso_datetime(arguments["end_time"])
            if start >= end:
                raise InvalidProposal("end_time must be later than start_time.")
    if action in {"update_calendar_event", "cancel_calendar_event"}:
        if not isinstance(arguments.get("event_id"), str) or not arguments["event_id"].strip():
            raise InvalidProposal("event_id must be a non-empty string.")
        arguments["event_id"] = arguments["event_id"].strip()
    if action == "update_calendar_event" and not any(
        field in arguments for field in ("title", "start_time", "end_time", "description", "timezone", "location")
    ):
        raise InvalidProposal("update_calendar_event must include at least one change.")
    if action in {"draft_email", "send_email"}:
        for field in ("to", "cc"):
            if field not in arguments:
                continue
            addresses = arguments[field] if isinstance(arguments[field], list) else [arguments[field]]
            if not addresses or any(
                not isinstance(address, str)
                or "@" not in address
                or address.strip().startswith("@")
                or address.strip().endswith("@")
                for address in addresses
            ):
                raise InvalidProposal(f"{field} must contain valid email addresses.")
            arguments[field] = [address.strip() for address in addresses] if isinstance(arguments[field], list) else arguments[field].strip()
        for field in ("subject", "body"):
            if not isinstance(arguments[field], str) or not arguments[field].strip():
                raise InvalidProposal(f"{field} must be a non-empty string.")
    return arguments


def _preconditions(action: str, arguments: Dict[str, Any], context: Dict[str, Any], objective: str) -> Dict[str, Any]:
    if action == "create_task" and _ensure_like(objective):
        return {"kind": "task_title_absent", "title": arguments["title"]}
    if action == "complete_task":
        task = next(item for item in context["tasks"] if item["id"] == arguments["task_id"])
        return {"kind": "task_unchanged", "task": dict(task)}
    if action == "update_task":
        task = next(item for item in context["tasks"] if item["id"] == arguments["task_id"])
        return {"kind": "task_unchanged", "task": dict(task)}
    if action == "create_reminder":
        matches = [
            item.get("id") for item in context["reminders"]
            if item.get("title") == arguments["title"]
            and item.get("reminder_time") == arguments["reminder_time"]
        ]
        return {
            "kind": "reminder_matches_unchanged",
            "title": arguments["title"],
            "reminder_time": arguments["reminder_time"],
            "ids": matches,
        }
    return {"kind": "none"}


def _validated_actions(
    raw_actions: Any,
    context: Dict[str, Any],
    objective: str,
) -> List[ProposedAction]:
    if not isinstance(raw_actions, list):
        raise InvalidProposal("Planner actions must be a list.")
    actions: List[ProposedAction] = []
    planned_ensure_titles = set()
    for order, raw in enumerate(raw_actions, start=1):
        if not isinstance(raw, dict) or set(raw) - {"action", "arguments"}:
            raise InvalidProposal("Each proposed action must contain only action and arguments.")
        action = raw.get("action")
        if not isinstance(action, str) or action not in _PROPOSED_ACTIONS:
            raise InvalidProposal(f"Unsupported proposed action: {action!r}.")
        arguments = _validate_arguments(action, raw.get("arguments", {}), context)
        preconditions = _preconditions(action, arguments, context, objective)

        # The same exact-title ensure guard used by direct execution applies to proposals.
        if preconditions["kind"] == "task_title_absent":
            normalized = _normalized_title(arguments["title"])
            if normalized in planned_ensure_titles:
                continue
            duplicate = next(
                (task for task in context["tasks"]
                 if _normalized_title(task.get("title", "")) == normalized),
                None,
            )
            if duplicate is not None:
                continue
            planned_ensure_titles.add(normalized)

        actions.append(ProposedAction(
            id=store.new_id(),
            order=len(actions) + 1,
            action=action,
            arguments=arguments,
            preconditions=preconditions,
        ))
    return actions


def create_proposal(objective: str, planner: Any) -> ApprovalRequest:
    cleaned = objective.strip()
    if not cleaned:
        raise InvalidProposal("Objective cannot be empty.")
    context = get_workspace_context()
    proposal = planner.propose_plan(cleaned, workspace_context=context)
    if not isinstance(proposal, dict):
        raise InvalidProposal("Planner returned an invalid proposal.")
    actions = _validated_actions(proposal.get("actions"), context, cleaned)
    message = proposal.get("message")
    if not isinstance(message, (str, type(None))):
        raise InvalidProposal("Planner message must be a string.")

    request = ApprovalRequest(
        id=store.new_id(),
        objective=cleaned,
        status="completed" if not actions else "pending_approval",
        actions=actions,
        message=message or ("No additional actions are necessary." if not actions else None),
        finished_at=utc_now() if not actions else None,
    )
    return store.create(request)


def get_proposal(approval_id: str) -> ApprovalRequest:
    request = store.get(approval_id)
    if request is None:
        raise ApprovalNotFound("Approval request not found.")
    return request


def list_proposals() -> List[ApprovalRequest]:
    return store.list_all()


def edit_proposal(approval_id: str, raw_actions: Any) -> ApprovalRequest:
    with _state_lock:
        request = get_proposal(approval_id)
        if request.status != "pending_approval":
            raise InvalidApprovalState("Only a pending proposal can be edited.")
        context = get_workspace_context()
        actions = _validated_actions(raw_actions, context, request.objective)
        request.actions = actions
        request.revision += 1
        request.status = "pending_approval" if actions else "completed"
        request.message = "No additional actions are necessary." if not actions else None
        request.updated_at = utc_now()
        request.finished_at = utc_now() if not actions else None
        return request


def reject_proposal(approval_id: str, reason: Optional[str] = None) -> ApprovalRequest:
    with _state_lock:
        request = get_proposal(approval_id)
        if request.status != "pending_approval":
            raise InvalidApprovalState("Only a pending proposal can be rejected.")
        request.status = "rejected"
        request.rejection_reason = reason
        request.updated_at = utc_now()
        request.finished_at = utc_now()
        return request


def _precondition_error(action: ProposedAction, context: Dict[str, Any]) -> Optional[str]:
    condition = action.preconditions
    kind = condition.get("kind")
    if kind == "task_title_absent":
        if any(
            _normalized_title(task.get("title", "")) == _normalized_title(condition["title"])
            for task in context["tasks"]
        ):
            return "A task with this exact title now exists. Review a refreshed proposal before execution."
    elif kind == "task_unchanged":
        expected = condition["task"]
        current = next((task for task in context["tasks"] if task.get("id") == expected.get("id")), None)
        if current != expected:
            return f"Task {expected.get('id')} changed after this proposal was created."
    elif kind == "reminder_matches_unchanged":
        current_ids = sorted(
            item.get("id") for item in context["reminders"]
            if item.get("title") == condition["title"]
            and item.get("reminder_time") == condition["reminder_time"]
        )
        if current_ids != sorted(condition["ids"]):
            return "Matching reminder state changed after this proposal was created."
    return None


def approve_proposal(approval_id: str, controller: Any) -> ApprovalRequest:
    # Lock through execution so concurrent/repeated requests cannot execute twice.
    with _state_lock:
        request = get_proposal(approval_id)
        if request.status != "pending_approval":
            if request.status in {"approved", "executing", "completed", "partially_completed", "failed"}:
                return request
            raise InvalidApprovalState(f"A proposal in state '{request.status}' cannot be approved.")

        context = get_workspace_context()
        stale_errors = [
            error for action in request.actions
            if (error := _precondition_error(action, context)) is not None
        ]
        if stale_errors:
            request.status = "stale"
            request.message = " ".join(stale_errors)
            request.updated_at = utc_now()
            request.finished_at = utc_now()
            return request

        request.status = "approved"
        request.approved_at = utc_now()
        request.updated_at = request.approved_at
        request.status = "executing"
        request.started_at = utc_now()

        execution = execute_approved_plan(
            objective=request.objective,
            approval_id=request.id,
            actions=request.actions,
            controller=controller,
            validate_action=lambda action: _precondition_error(
                action,
                get_workspace_context(),
            ),
        )
        workflow = execution["workflow"]
        run = execution["run"]
        request.workflow_id = workflow.id
        request.run_id = run.id
        request.status = {
            "completed": "completed",
            "partially_completed": "partially_completed",
            "failed": "failed",
        }[workflow.status]
        request.message = run.final_message
        request.updated_at = utc_now()
        request.finished_at = request.updated_at
        return request
