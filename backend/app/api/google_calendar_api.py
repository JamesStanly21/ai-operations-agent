from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.integrations.calendar.oauth import GoogleCalendarOAuthError, oauth_manager
from app.integrations.registry import reset_calendar_adapter


router = APIRouter(prefix="/integrations/google/calendar", tags=["Google Calendar"])


@router.get("/connect")
def connect_google_calendar():
    try:
        authorization_url = oauth_manager.create_authorization_url()
    except GoogleCalendarOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(authorization_url, status_code=302)


@router.get("/callback")
def google_calendar_callback(state: str, code: str | None = None, error: str | None = None):
    if error:
        raise HTTPException(status_code=400, detail="Google Calendar authorization was not completed.")
    try:
        oauth_manager.exchange_code(state, code or "")
    except GoogleCalendarOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    reset_calendar_adapter()
    return {"connected": True, "provider": "google_calendar", "execution_mode": "live"}


@router.get("/status")
def google_calendar_status():
    return oauth_manager.status()


@router.post("/disconnect")
def disconnect_google_calendar():
    try:
        oauth_manager.credentials_store.disconnect()
    except GoogleCalendarOAuthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    reset_calendar_adapter()
    return {"connected": False, "provider": None, "execution_mode": "simulated"}
