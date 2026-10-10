"""Read-only view of the existing in-memory workspace state."""

from typing import Any, Dict, Optional

from app.tools.reminders_tool import get_reminders
from app.tools.tasks_tool import get_tasks
from app.workflows import store


def get_workspace_context(
    exclude_workflow_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a compact snapshot without maintaining a second source of truth."""
    tasks = [
        {
            "id": task.get("id"),
            "title": task.get("title"),
            "status": task.get("status"),
            **({"description": task["description"]} if task.get("description") else {}),
        }
        for task in get_tasks().get("tasks", [])
    ]
    reminders = [
        {
            "id": reminder.get("id"),
            "title": reminder.get("title"),
            "reminder_time": reminder.get("reminder_time"),
            "status": reminder.get("status"),
        }
        for reminder in get_reminders().get("reminders", [])
    ]

    workflows = []
    for workflow in store.list_workflows():
        if workflow.id == exclude_workflow_id:
            continue

        latest_run = store.get_run(workflow.run_ids[-1]) if workflow.run_ids else None
        run_steps = store.get_steps(latest_run) if latest_run is not None else []
        step_summaries = [
            {
                "title": step.title,
                "action": step.action,
                "status": step.status,
                "error": step.error,
                "resource_refs": step.resource_refs,
            }
            for step in run_steps
        ]
        workflows.append({
            "id": workflow.id,
            "title": workflow.title,
            "objective": workflow.objective,
            "status": workflow.status,
            "latest_run": (
                {
                    "status": latest_run.status,
                    "final_message": latest_run.final_message,
                }
                if latest_run is not None
                else None
            ),
            "steps": step_summaries,
            "failures": [
                {"title": step.title, "error": step.error}
                for step in run_steps
                if step.status == "failed" or step.error
            ],
        })

    return {
        "tasks": tasks,
        "reminders": reminders,
        "workflows": workflows,
    }
