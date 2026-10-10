from typing import Any, Callable, Dict, Optional
import re
from datetime import datetime, timezone

from app.agent.planner import AgentPlanner
from app.agent.controller import AgentController
from app.agent.workspace_context import get_workspace_context


class OperationsAgent:

    def __init__(self):
        self.planner = AgentPlanner()
        self.controller = AgentController()

    def run(
        self,
        instruction: str,
        max_steps: int = 8,
        step_callback: Optional[Callable[[int, Any, Dict[str, Any], Dict[str, Any], datetime], None]] = None,
        context_exclude_workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:

        history = []
        steps = []
        workspace_context = get_workspace_context(
            exclude_workflow_id=context_exclude_workflow_id
        )

        for step_number in range(1, max_steps + 1):

            # 1. Ask the AI what to do NEXT
            decision = self.planner.next_action(
                instruction,
                history,
                workspace_context=workspace_context,
            )

            # 2. If the AI says the objective is complete
            if decision.action == "done":

                return {
                    "success": True,
                    "instruction": instruction,
                    "steps": steps,
                    "final_message": decision.message
                    or "Workflow completed successfully.",
                }

            # 3. Build tool arguments
            arguments = {}

            if decision.title is not None:
                arguments["title"] = decision.title

            if decision.description is not None:
                arguments["description"] = decision.description

            if decision.task_id is not None:
                arguments["task_id"] = decision.task_id

            if decision.reminder_time is not None:
                arguments["reminder_time"] = decision.reminder_time

            # Avoid exact-title duplicates for ensure/prepare/check objectives.
            if decision.action == "create_task" and self._should_guard_duplicate(instruction):
                existing_task = next(
                    (
                        task for task in workspace_context.get("tasks", [])
                        if self._normalized_title(task.get("title"))
                        == self._normalized_title(decision.title)
                    ),
                    None,
                )
                if existing_task is not None:
                    result = {
                        "success": True,
                        "tool": "create_task",
                        "result": {
                            "success": True,
                            "already_exists": True,
                            "message": "An exact-title task already exists; no duplicate was created.",
                            "task": existing_task,
                        },
                    }
                    step_started_at = datetime.now(timezone.utc)
                    step_record = {
                        "step": step_number,
                        "action": decision.model_dump(),
                        "observation": result,
                    }
                    steps.append(step_record)
                    if step_callback is not None:
                        step_callback(step_number, decision, arguments, result, step_started_at)
                    history.append(step_record)
                    workspace_context = get_workspace_context()
                    continue

            # 4. Execute ONE tool
            step_started_at = datetime.now(timezone.utc)
            execution = self.controller.execute_plan([
                {
                    "tool": decision.action,
                    "arguments": arguments,
                }
            ])

            # 5. Extract the tool result
            result = execution["results"][0]["result"]

            # 6. Record what happened
            step_record = {
                "step": step_number,
                "action": decision.model_dump(),
                "observation": result,
            }

            steps.append(step_record)

            if step_callback is not None:
                step_callback(step_number, decision, arguments, result, step_started_at)

            # 7. Give the result back to the AI
            history.append(step_record)

            # 8. If the tool failed, let the AI react to the failure
            if not result.get("success", False):
                history.append({
                    "step": step_number,
                    "type": "tool_failure",
                    "message": result.get(
                        "error",
                        "Tool execution failed."
                    ),
                })

            # Refresh from the live source of truth before the next PLAN step.
            workspace_context = get_workspace_context()

        return {
            "success": False,
            "instruction": instruction,
            "steps": steps,
            "final_message": (
                "The agent reached the maximum number "
                "of execution steps."
            ),
        }

    @staticmethod
    def _normalized_title(title: Optional[str]) -> str:
        return " ".join((title or "").split()).casefold()

    @staticmethod
    def _should_guard_duplicate(instruction: str) -> bool:
        explicit_creation = re.search(
            r"\b(?:create|add)\b.*\btask\b|\bmake\s+(?:me\s+)?(?:another|a|one|new)\s+task\b",
            instruction,
            re.IGNORECASE,
        )
        ensure_like = re.search(
            r"\b(?:ensure|prepare|check|verify|confirm)\b|\bmake\s+sure\b",
            instruction,
            re.IGNORECASE,
        )
        return bool(ensure_like and not explicit_creation)
