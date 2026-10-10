"""Adapter registry. Real providers can be injected without changing tools/router."""

from app.integrations.calendar.mock import MockCalendarAdapter
from app.integrations.email.mock import MockEmailAdapter


_mock_calendar_adapter = MockCalendarAdapter()
_calendar_adapter_override = None
_google_calendar_adapter = None
calendar_adapter = _mock_calendar_adapter
email_adapter = MockEmailAdapter()


def get_calendar_adapter():
    if _calendar_adapter_override is not None:
        return _calendar_adapter_override
    from app.integrations.calendar.oauth import oauth_manager

    if oauth_manager.credentials_store.is_connected():
        global _google_calendar_adapter
        if _google_calendar_adapter is None:
            from app.integrations.calendar.google import GoogleCalendarAdapter
            _google_calendar_adapter = GoogleCalendarAdapter()
        return _google_calendar_adapter
    return _mock_calendar_adapter


def get_email_adapter():
    return email_adapter


def set_calendar_adapter(adapter) -> None:
    global calendar_adapter, _calendar_adapter_override
    _calendar_adapter_override = adapter
    calendar_adapter = adapter


def reset_calendar_adapter() -> None:
    global calendar_adapter, _calendar_adapter_override
    _calendar_adapter_override = None
    calendar_adapter = _mock_calendar_adapter


def set_email_adapter(adapter) -> None:
    global email_adapter
    email_adapter = adapter
