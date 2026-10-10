from typing import Any, Dict

from app.tools.tasks_tool import (
    create_task,
    get_tasks,
    complete_task,
    update_task,
)

from app.tools.reminders_tool import (
    create_reminder,
    get_reminders,
)
from app.integrations.calendar.tools import (
    cancel_calendar_event,
    create_calendar_event,
    get_calendar_events,
    update_calendar_event,
)
from app.integrations.email.tools import draft_email, send_email
from app.approvals import store as approval_store


TOOLS = {
    "create_task": create_task,
    "get_tasks": get_tasks,
    "complete_task": complete_task,
    "update_task": update_task,
    "create_reminder": create_reminder,
    "get_reminders": get_reminders,
    "create_calendar_event": create_calendar_event,
    "get_calendar_events": get_calendar_events,
    "update_calendar_event": update_calendar_event,
    "cancel_calendar_event": cancel_calendar_event,
    "draft_email": draft_email,
    "send_email": send_email,
}

APPROVAL_REQUIRED_TOOLS = {
    "create_calendar_event",
    "update_calendar_event",
    "cancel_calendar_event",
    "draft_email",
    "send_email",
}


def _approval_error(tool_name: str, arguments: Dict[str, Any], approval_id: str | None, action_id: str | None):
    if tool_name not in APPROVAL_REQUIRED_TOOLS:
        return None
    approval = approval_store.get(approval_id) if approval_id else None
    if approval is None or approval.status != "executing":
        return f"{tool_name} requires an executing approved proposal."
    action = next((item for item in approval.actions if item.id == action_id), None)
    if action is None or action.status != "pending":
        return "The approved action is missing, altered, or already used."
    if action.action != tool_name or action.arguments != arguments:
        return "The requested tool call does not match the approved action."
    return None


def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    approval_id: str | None = None,
    approval_action_id: str | None = None,
) -> Dict[str, Any]:

    authorization_error = _approval_error(
        tool_name,
        arguments,
        approval_id,
        approval_action_id,
    )
    if authorization_error:
        return {"success": False, "tool": tool_name, "error": authorization_error}

    tool = TOOLS.get(tool_name)

    if tool is None:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}",
        }

    try:
        result = tool(**arguments)

        return {
            "success": result.get("success", True),
            "tool": tool_name,
            "result": result,
        }

    except Exception as e:
        return {
            "success": False,
            "tool": tool_name,
            "error": str(e),
        }


def list_tools():
    return list(TOOLS.keys())
