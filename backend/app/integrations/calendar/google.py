from typing import Any, Dict

from app.integrations.base import operation_result
from app.integrations.calendar.oauth import GoogleCalendarOAuthError, oauth_manager


DEFAULT_CALENDAR_TIMEZONE = "Asia/Kolkata"


def build_calendar_service(credentials: Any):
    try:
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GoogleCalendarOAuthError(
            "Google Calendar libraries are not installed. Install backend requirements."
        ) from exc
    authorized_http = AuthorizedHttp(credentials, http=httplib2.Http())
    return build("calendar", "v3", http=authorized_http, cache_discovery=False)


class GoogleCalendarAdapter:
    provider_name = "google_calendar"
    execution_mode = "live"

    def __init__(self, credentials_provider=None, service_builder=None):
        self.credentials_provider = credentials_provider or oauth_manager.credentials_store.load
        self.service_builder = service_builder or build_calendar_service

    def _service(self):
        try:
            credentials = self.credentials_provider()
        except GoogleCalendarOAuthError:
            raise
        except Exception:
            raise GoogleCalendarOAuthError(
                "Google Calendar authorization failed; reconnect the account."
            ) from None
        return self.service_builder(credentials)

    @staticmethod
    def _event_body(arguments: Dict[str, Any]) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if "title" in arguments:
            body["summary"] = arguments["title"]
        if "description" in arguments:
            body["description"] = arguments["description"]
        if "location" in arguments:
            body["location"] = arguments["location"]
        timezone_name = arguments.get("timezone") or DEFAULT_CALENDAR_TIMEZONE
        if "start_time" in arguments:
            start = arguments["start_time"]
            is_date = isinstance(start, str) and len(start) == 10 and start[4:5] == "-" and start[7:8] == "-"
            body["start"] = {"date": start} if is_date else {"dateTime": start}
            if "dateTime" in body["start"]:
                body["start"]["timeZone"] = timezone_name
        if "end_time" in arguments:
            end = arguments["end_time"]
            is_date = isinstance(end, str) and len(end) == 10 and end[4:5] == "-" and end[7:8] == "-"
            body["end"] = {"date": end} if is_date else {"dateTime": end}
            if "dateTime" in body["end"]:
                body["end"]["timeZone"] = timezone_name
        return body

    def create_event(self, **arguments: Any) -> Dict[str, Any]:
        event = self._service().events().insert(
            calendarId="primary",
            body=self._event_body(arguments),
        ).execute()
        return operation_result(self, success=True, message="Google Calendar event created.", event=event)

    def get_events(self, **arguments: Any) -> Dict[str, Any]:
        query: Dict[str, Any] = {
            "calendarId": "primary",
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if arguments.get("start_time"):
            query["timeMin"] = arguments["start_time"]
        if arguments.get("end_time"):
            query["timeMax"] = arguments["end_time"]
        result = self._service().events().list(**query).execute()
        return operation_result(
            self,
            success=True,
            message="Google Calendar events retrieved.",
            events=result.get("items", []),
        )

    def update_event(self, event_id: str, **changes: Any) -> Dict[str, Any]:
        service = self._service()
        body = self._event_body(changes)
        if changes.get("timezone") and not ("start_time" in changes or "end_time" in changes):
            current = service.events().get(calendarId="primary", eventId=event_id).execute()
            for field in ("start", "end"):
                if field in current and "dateTime" in current[field]:
                    body[field] = {**current[field], "timeZone": changes["timezone"]}
        elif ("start_time" in changes) != ("end_time" in changes):
            # A timed update carries both boundaries, so Google receives a
            # complete interval with the same explicit timezone on each end.
            current = service.events().get(calendarId="primary", eventId=event_id).execute()
            for field in ("start", "end"):
                if field not in body and field in current:
                    if "dateTime" in current[field]:
                        body[field] = {
                            **current[field],
                            "timeZone": changes.get("timezone") or DEFAULT_CALENDAR_TIMEZONE,
                        }
                    elif "date" in current[field]:
                        body[field] = current[field]
        event = service.events().patch(
            calendarId="primary",
            eventId=event_id,
            body=body,
        ).execute()
        return operation_result(self, success=True, message="Google Calendar event updated.", event=event)

    def cancel_event(self, event_id: str) -> Dict[str, Any]:
        self._service().events().delete(calendarId="primary", eventId=event_id).execute()
        return operation_result(
            self,
            success=True,
            message="Google Calendar event cancelled.",
            event={"id": event_id, "status": "cancelled"},
        )
