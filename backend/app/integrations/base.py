from typing import Any, Dict, List, Protocol


class CalendarAdapter(Protocol):
    provider_name: str
    execution_mode: str

    def create_event(self, **arguments: Any) -> Dict[str, Any]: ...
    def get_events(self, **arguments: Any) -> Dict[str, Any]: ...
    def update_event(self, **arguments: Any) -> Dict[str, Any]: ...
    def cancel_event(self, **arguments: Any) -> Dict[str, Any]: ...


class EmailAdapter(Protocol):
    provider_name: str
    execution_mode: str

    def draft_email(self, **arguments: Any) -> Dict[str, Any]: ...
    def send_email(self, **arguments: Any) -> Dict[str, Any]: ...


def operation_result(
    adapter: Any,
    *,
    success: bool,
    message: str,
    **payload: Any,
) -> Dict[str, Any]:
    return {
        "success": success,
        "message": message,
        "execution_mode": adapter.execution_mode,
        "provider": adapter.provider_name,
        "simulated": adapter.execution_mode == "simulated",
        **payload,
    }
