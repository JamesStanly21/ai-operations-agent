from typing import Any, Dict

from app.integrations.registry import get_calendar_adapter


def create_calendar_event(**arguments: Any) -> Dict[str, Any]:
    return get_calendar_adapter().create_event(**arguments)


def get_calendar_events(**arguments: Any) -> Dict[str, Any]:
    return get_calendar_adapter().get_events(**arguments)


def update_calendar_event(**arguments: Any) -> Dict[str, Any]:
    return get_calendar_adapter().update_event(**arguments)


def cancel_calendar_event(**arguments: Any) -> Dict[str, Any]:
    return get_calendar_adapter().cancel_event(**arguments)
