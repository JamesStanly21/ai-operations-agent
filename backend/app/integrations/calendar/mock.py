from typing import Any, Dict, List

from app.integrations.base import operation_result


class MockCalendarAdapter:
    provider_name = "mock-calendar"
    execution_mode = "simulated"

    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def create_event(self, **arguments: Any) -> Dict[str, Any]:
        event = {
            "id": f"event-{len(self.events) + 1}",
            **arguments,
            "status": "scheduled",
        }
        self.events.append(event)
        return operation_result(self, success=True, message="Calendar event created (simulated).", event=event)

    def get_events(self, **arguments: Any) -> Dict[str, Any]:
        start = arguments.get("start_time")
        end = arguments.get("end_time")
        events = [
            event for event in self.events
            if event["status"] != "cancelled"
            and (start is None or event.get("start_time", "") >= start)
            and (end is None or event.get("start_time", "") <= end)
        ]
        return operation_result(self, success=True, message="Calendar events retrieved (simulated).", events=events)

    def update_event(self, event_id: str, **changes: Any) -> Dict[str, Any]:
        event = next((item for item in self.events if item["id"] == event_id), None)
        if event is None or event["status"] == "cancelled":
            return operation_result(self, success=False, message=f"Calendar event {event_id} was not found.", error=f"Calendar event {event_id} was not found.")
        event.update(changes)
        return operation_result(self, success=True, message="Calendar event updated (simulated).", event=event)

    def cancel_event(self, event_id: str) -> Dict[str, Any]:
        event = next((item for item in self.events if item["id"] == event_id), None)
        if event is None or event["status"] == "cancelled":
            return operation_result(self, success=False, message=f"Calendar event {event_id} was not found.", error=f"Calendar event {event_id} was not found.")
        event["status"] = "cancelled"
        return operation_result(self, success=True, message="Calendar event cancelled (simulated).", event=event)
