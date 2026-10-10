"""Google Calendar OAuth and local credential storage.

OAuth state is short-lived and in-memory. Authorized-user credentials are stored
outside the repository with restrictive file permissions.
"""

import json
import os
import secrets
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import load_environment


load_environment()


CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
STATE_TTL_SECONDS = 600


class GoogleCalendarOAuthError(Exception):
    pass


def _client_config() -> Dict[str, Any]:
    # Resolve the backend file at use time as well as app startup. This covers
    # Uvicorn processes imported before local OAuth settings were added.
    load_environment()
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not client_id or not client_secret or not redirect_uri:
        raise GoogleCalendarOAuthError(
            "Google Calendar OAuth is not configured. Set GOOGLE_CLIENT_ID, "
            "GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI."
        )
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def create_oauth_flow(state: Optional[str] = None):
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise GoogleCalendarOAuthError(
            "Google Calendar libraries are not installed. Install backend requirements."
        ) from exc
    flow = Flow.from_client_config(
        _client_config(),
        scopes=CALENDAR_SCOPES,
        state=state,
    )
    flow.redirect_uri = os.environ["GOOGLE_REDIRECT_URI"]
    return flow


def credentials_from_authorized_user_info(info: Dict[str, Any]):
    try:
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise GoogleCalendarOAuthError(
            "Google Calendar libraries are not installed. Install backend requirements."
        ) from exc
    return Credentials.from_authorized_user_info(info, scopes=CALENDAR_SCOPES)


def google_refresh_request():
    try:
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise GoogleCalendarOAuthError(
            "Google Calendar libraries are not installed. Install backend requirements."
        ) from exc
    return Request()


class CalendarCredentialsStore:
    def __init__(self, path: Optional[Path] = None):
        configured_path = os.getenv("GOOGLE_TOKEN_FILE")
        self.path = Path(path or configured_path or (Path.home() / ".opsagent" / "google_calendar_token.json"))

    def _read_info(self) -> Optional[Dict[str, Any]]:
        try:
            with self.path.open("r", encoding="utf-8") as token_file:
                info = json.load(token_file)
            return info if isinstance(info, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def is_connected(self) -> bool:
        info = self._read_info()
        if not info:
            return False
        if info.get("refresh_token"):
            return True
        expiry = info.get("expiry")
        if not isinstance(expiry, str):
            return False
        try:
            expires_at = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            return expires_at > datetime.now(timezone.utc)
        except ValueError:
            return False

    def save(self, credentials: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = credentials.to_json()
        temporary_path = None
        try:
            fd, temporary_name = tempfile.mkstemp(
                prefix=".google-calendar-",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            temporary_path = Path(temporary_name)
            self._restrict_permissions(temporary_path)
            with os.fdopen(fd, "w", encoding="utf-8") as token_file:
                token_file.write(serialized)
                token_file.flush()
                os.fsync(token_file.fileno())
            os.replace(temporary_path, self.path)
            self._restrict_permissions(self.path)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _restrict_permissions(path: Path) -> None:
        # On Windows chmod(0600) removes write permission instead of setting
        # a POSIX-style ACL. The default token location is under the user's
        # profile, where inherited Windows ACLs restrict access to that user.
        if os.name != "nt":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    def load(self):
        info = self._read_info()
        if not info:
            raise GoogleCalendarOAuthError("Google Calendar is not connected.")
        credentials = credentials_from_authorized_user_info(info)
        if getattr(credentials, "expired", False):
            if not getattr(credentials, "refresh_token", None):
                raise GoogleCalendarOAuthError("Google Calendar credentials expired; reconnect the account.")
            try:
                credentials.refresh(google_refresh_request())
            except Exception:
                raise GoogleCalendarOAuthError(
                    "Google Calendar authorization could not be refreshed; reconnect the account."
                ) from None
            self.save(credentials)
        if not getattr(credentials, "valid", True):
            raise GoogleCalendarOAuthError("Google Calendar credentials are invalid; reconnect the account.")
        return credentials

    def disconnect(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise GoogleCalendarOAuthError("Could not remove the saved Google Calendar connection.") from exc


class GoogleCalendarOAuth:
    def __init__(self, credentials_store: Optional[CalendarCredentialsStore] = None):
        self.credentials_store = credentials_store or CalendarCredentialsStore()
        self._states: Dict[str, float] = {}
        self._code_verifiers: Dict[str, str] = {}

    @staticmethod
    def ensure_configured() -> None:
        _client_config()

    def create_authorization_url(self) -> str:
        flow = create_oauth_flow()
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        if not state:
            raise GoogleCalendarOAuthError("Google OAuth did not return a state value.")
        now = time.time()
        self._states = {
            key: created for key, created in self._states.items()
            if now - created <= STATE_TTL_SECONDS
        }
        self._code_verifiers = {
            key: verifier for key, verifier in self._code_verifiers.items()
            if key in self._states
        }
        self._states[state] = now
        code_verifier = getattr(flow, "code_verifier", None)
        if code_verifier:
            self._code_verifiers[state] = code_verifier
        return authorization_url

    def exchange_code(self, state: str, code: str) -> None:
        created = self._states.pop(state, None)
        code_verifier = self._code_verifiers.pop(state, None)
        if created is None or time.time() - created > STATE_TTL_SECONDS:
            raise GoogleCalendarOAuthError("OAuth state is missing, expired, or invalid.")
        if not code:
            raise GoogleCalendarOAuthError("Google did not return an authorization code.")
        flow = create_oauth_flow(state=state)
        try:
            # Google auth's PKCE verifier belongs to the Flow that generated
            # the authorization URL. Restore it on the callback Flow so the
            # token exchange can prove possession of the original verifier.
            if code_verifier:
                flow.code_verifier = code_verifier
            flow.fetch_token(code=code)
            self.credentials_store.save(flow.credentials)
        except Exception:
            raise GoogleCalendarOAuthError(
                "Google Calendar authorization could not be completed. Check OAuth configuration and try again."
            ) from None

    def status(self) -> Dict[str, Any]:
        connected = self.credentials_store.is_connected()
        return {
            "connected": connected,
            "provider": "google_calendar" if connected else None,
            "execution_mode": "live" if connected else "simulated",
            "scopes": CALENDAR_SCOPES if connected else [],
        }


oauth_manager = GoogleCalendarOAuth()
