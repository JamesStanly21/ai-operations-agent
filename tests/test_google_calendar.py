import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.api import google_calendar_api
from app.agent.controller import AgentController
from app.approvals import store as approval_store
from app.approvals.service import approve_proposal, create_proposal
from app.integrations import registry
from app.integrations.calendar.google import GoogleCalendarAdapter
from app.integrations.calendar import oauth
from app.integrations.calendar.mock import MockCalendarAdapter
from app.tools import reminders_tool, tasks_tool
from app.workflows import store as workflow_store


class MemoryCredentialsStore:
    def __init__(self):
        self.credentials = None

    def save(self, credentials):
        self.credentials = credentials

    def load(self):
        return self.credentials

    def is_connected(self):
        return self.credentials is not None

    def disconnect(self):
        self.credentials = None


class FakeCredentials:
    def __init__(self, expired=False, refresh_token="refresh-test"):
        self.expired = expired
        self.refresh_token = refresh_token
        self.valid = not expired
        self.refresh_calls = 0

    def refresh(self, request):
        self.refresh_calls += 1
        self.expired = False
        self.valid = True

    def to_json(self):
        return json.dumps({
            "token": "access-test",
            "refresh_token": self.refresh_token,
            "expiry": "2099-01-01T00:00:00Z",
        })


class FakeOAuthFlow:
    def __init__(self, state="state-123", credentials=None, code_verifier=None):
        self.state = state
        self.credentials = credentials or FakeCredentials()
        self.code_verifier = code_verifier
        self.fetch_code = None
        self.fetch_verifier = None
        self.authorization_options = None

    def authorization_url(self, **kwargs):
        self.authorization_options = kwargs
        return "https://accounts.google.test/auth?state=state-123", self.state

    def fetch_token(self, code):
        self.fetch_code = code
        self.fetch_verifier = self.code_verifier


class FakeRequest:
    def __init__(self, result=None, error=None):
        self.result = result or {}
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class FakeEventsApi:
    def __init__(self):
        self.calls = []
        self.responses = {}

    def _request(self, method, **kwargs):
        self.calls.append((method, kwargs))
        return FakeRequest(self.responses.get(method, {}))

    def insert(self, **kwargs): return self._request("insert", **kwargs)
    def list(self, **kwargs): return self._request("list", **kwargs)
    def get(self, **kwargs): return self._request("get", **kwargs)
    def patch(self, **kwargs): return self._request("patch", **kwargs)
    def delete(self, **kwargs): return self._request("delete", **kwargs)


class FakeCalendarService:
    def __init__(self):
        self.api = FakeEventsApi()

    def events(self):
        return self.api


class FixedPlanner:
    def __init__(self, actions):
        self.actions = actions

    def propose_plan(self, _objective, workspace_context=None):
        return {"actions": self.actions, "message": "Approved calendar action."}


class GoogleCalendarTests(unittest.TestCase):
    def setUp(self):
        registry.reset_calendar_adapter()
        tasks_tool.tasks.clear()
        reminders_tool.reminders.clear()
        approval_store.approval_requests.clear()
        workflow_store.workflows.clear()
        workflow_store.agent_runs.clear()
        workflow_store.workflow_steps.clear()
        self.memory_store = MemoryCredentialsStore()
        self.manager = oauth.GoogleCalendarOAuth(self.memory_store)
        self.old_manager = google_calendar_api.oauth_manager
        google_calendar_api.oauth_manager = self.manager
        self.flow = FakeOAuthFlow()

    def tearDown(self):
        google_calendar_api.oauth_manager = self.old_manager
        registry.reset_calendar_adapter()
        tasks_tool.tasks.clear()
        reminders_tool.reminders.clear()
        approval_store.approval_requests.clear()
        workflow_store.workflows.clear()
        workflow_store.agent_runs.clear()
        workflow_store.workflow_steps.clear()

    def test_connect_url_requests_only_calendar_events_scope_and_stores_state(self):
        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "client-id-test",
            "GOOGLE_CLIENT_SECRET": "client-secret-test",
            "GOOGLE_REDIRECT_URI": "http://localhost/callback",
        }), patch.object(oauth, "create_oauth_flow", return_value=self.flow):
            url = self.manager.create_authorization_url()

        self.assertIn("accounts.google.test/auth", url)
        self.assertEqual(self.manager._states, {"state-123": next(iter(self.manager._states.values()))})
        self.assertEqual(oauth.CALENDAR_SCOPES, ["https://www.googleapis.com/auth/calendar.events"])
        self.assertEqual(self.flow.authorization_options["access_type"], "offline")
        self.assertEqual(self.flow.authorization_options["prompt"], "consent")

    def test_connect_endpoint_redirects_to_google(self):
        with patch.object(oauth, "create_oauth_flow", return_value=self.flow):
            response = google_calendar_api.connect_google_calendar()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "https://accounts.google.test/auth?state=state-123")

    def test_state_validation_and_callback_code_exchange(self):
        self.manager._states["valid-state"] = oauth.time.time()
        with patch.object(oauth, "create_oauth_flow", return_value=self.flow):
            with self.assertRaises(oauth.GoogleCalendarOAuthError):
                self.manager.exchange_code("wrong-state", "auth-code")
            self.manager.exchange_code("valid-state", "auth-code")

        self.assertEqual(self.flow.fetch_code, "auth-code")
        self.assertIs(self.memory_store.credentials, self.flow.credentials)
        self.assertNotIn("valid-state", self.manager._states)

    def test_callback_endpoint_returns_only_connection_status(self):
        self.manager._states["valid-state"] = oauth.time.time()
        with patch.object(oauth, "create_oauth_flow", return_value=self.flow):
            result = google_calendar_api.google_calendar_callback("valid-state", "auth-code")
        self.assertEqual(result, {
            "connected": True,
            "provider": "google_calendar",
            "execution_mode": "live",
        })
        self.assertNotIn("token", str(result).lower())

    def test_callback_restores_pkce_verifier_for_token_exchange(self):
        authorization_flow = FakeOAuthFlow(code_verifier="fixture-pkce-verifier")
        callback_flow = FakeOAuthFlow(code_verifier=None)
        with patch.object(
            oauth,
            "create_oauth_flow",
            side_effect=[authorization_flow, callback_flow],
        ):
            self.manager.create_authorization_url()
            result = google_calendar_api.google_calendar_callback(
                "state-123", "fixture-authorization-code"
            )

        self.assertEqual(result["connected"], True)
        self.assertEqual(callback_flow.fetch_verifier, "fixture-pkce-verifier")
        self.assertIs(self.memory_store.credentials, callback_flow.credentials)

    def test_credentials_refresh_and_secure_file_storage(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp_dir:
            store = oauth.CalendarCredentialsStore(Path(temp_dir) / "token.json")
            store.path.write_text(json.dumps({"refresh_token": "refresh-test"}), encoding="utf-8")
            credentials = FakeCredentials(expired=True)
            with patch.object(oauth, "credentials_from_authorized_user_info", return_value=credentials), \
                 patch.object(oauth, "google_refresh_request", return_value=object()):
                loaded = store.load()
            self.assertIs(loaded, credentials)
            self.assertEqual(credentials.refresh_calls, 1)
            self.assertTrue(store.path.exists())
            self.assertIn("access-test", store.path.read_text(encoding="utf-8"))

    def test_google_adapter_calendar_operations_and_live_metadata(self):
        service = FakeCalendarService()
        service.api.responses.update({
            "insert": {"id": "google-event-1", "summary": "Demo"},
            "list": {"items": [{"id": "google-event-1", "summary": "Demo"}]},
            "get": {"id": "google-event-1", "start": {"dateTime": "2026-10-12T09:00:00Z"}, "end": {"dateTime": "2026-10-12T10:00:00Z"}},
            "patch": {"id": "google-event-1", "summary": "Updated demo"},
            "delete": {},
        })
        adapter = GoogleCalendarAdapter(
            credentials_provider=lambda: object(),
            service_builder=lambda _credentials: service,
        )
        created = adapter.create_event(
            title="Demo",
            start_time="2026-10-12T09:00:00Z",
            end_time="2026-10-12T10:00:00Z",
        )
        events = adapter.get_events(start_time="2026-10-12T00:00:00Z")
        updated = adapter.update_event(
            "google-event-1",
            title="Updated demo",
            start_time="2026-10-12T10:00:00",
            end_time="2026-10-12T11:00:00",
        )
        cancelled = adapter.cancel_event("google-event-1")

        self.assertEqual(created["execution_mode"], "live")
        self.assertEqual(created["provider"], "google_calendar")
        self.assertFalse(created["simulated"])
        self.assertEqual(created["event"]["id"], "google-event-1")
        self.assertEqual(events["events"][0]["id"], "google-event-1")
        self.assertEqual(updated["event"]["summary"], "Updated demo")
        self.assertEqual(cancelled["event"]["id"], "google-event-1")
        self.assertEqual([call[0] for call in service.api.calls], ["insert", "list", "patch", "delete"])
        insert_body = service.api.calls[0][1]["body"]
        self.assertEqual(insert_body["summary"], "Demo")
        self.assertEqual(insert_body["start"]["timeZone"], "Asia/Kolkata")
        self.assertEqual(insert_body["end"]["timeZone"], "Asia/Kolkata")
        update_body = next(call[1]["body"] for call in service.api.calls if call[0] == "patch")
        self.assertEqual(update_body["start"]["timeZone"], "Asia/Kolkata")
        self.assertEqual(update_body["end"]["timeZone"], "Asia/Kolkata")
        self.assertEqual(update_body["start"]["dateTime"], "2026-10-12T10:00:00")
        self.assertEqual(service.api.calls[3][1]["eventId"], "google-event-1")

    def test_google_adapter_keeps_all_day_events_date_only(self):
        body = GoogleCalendarAdapter._event_body({
            "start_time": "2026-10-12",
            "end_time": "2026-10-13",
        })
        self.assertEqual(body["start"], {"date": "2026-10-12"})
        self.assertEqual(body["end"], {"date": "2026-10-13"})

    def test_approved_google_calendar_action_is_recorded_in_workflow(self):
        service = FakeCalendarService()
        service.api.responses["insert"] = {"id": "google-event-real-id", "summary": "Demo"}
        adapter = GoogleCalendarAdapter(lambda: object(), lambda _credentials: service)
        registry.set_calendar_adapter(adapter)
        approval = create_proposal("Schedule the demo", FixedPlanner([{
            "action": "create_calendar_event",
            "arguments": {
                "title": "Demo",
                "start_time": "2026-10-12T09:00:00Z",
                "end_time": "2026-10-12T10:00:00Z",
            },
        }]))

        result = approve_proposal(approval.id, AgentController())
        workflow = workflow_store.get_workflow(result.workflow_id)
        run = workflow_store.get_run(result.run_id)
        step = workflow_store.get_steps(run)[0]
        self.assertEqual(result.status, "completed")
        self.assertEqual(workflow.source_approval_id, approval.id)
        self.assertEqual(step.approval_action_id, approval.actions[0].id)
        self.assertEqual(step.resource_refs, ["google-event-real-id"])
        self.assertEqual(step.result["result"]["execution_mode"], "live")

    def test_provider_failure_propagates_for_workflow_failure_recording(self):
        service = FakeCalendarService()
        service.api.responses["insert"] = None
        service.api.insert = lambda **_kwargs: FakeRequest(error=RuntimeError("Google unavailable"))
        adapter = GoogleCalendarAdapter(lambda: object(), lambda _credentials: service)
        with self.assertRaisesRegex(RuntimeError, "Google unavailable"):
            adapter.create_event(
                title="Demo",
                start_time="2026-10-12T09:00:00Z",
                end_time="2026-10-12T10:00:00Z",
            )

    def test_registry_uses_mock_when_disconnected_and_google_when_connected(self):
        with patch.object(oauth.oauth_manager.credentials_store, "is_connected", return_value=False):
            self.assertIsInstance(registry.get_calendar_adapter(), MockCalendarAdapter)
        with patch.object(oauth.oauth_manager.credentials_store, "is_connected", return_value=True):
            self.assertIsInstance(registry.get_calendar_adapter(), GoogleCalendarAdapter)

    def test_status_and_disconnect_do_not_expose_credentials(self):
        self.memory_store.credentials = FakeCredentials()
        status = google_calendar_api.google_calendar_status()
        self.assertTrue(status["connected"])
        self.assertEqual(status["execution_mode"], "live")
        self.assertNotIn("client_secret", str(status))
        disconnected = google_calendar_api.disconnect_google_calendar()
        self.assertFalse(disconnected["connected"])
        self.assertIsNone(self.memory_store.credentials)


if __name__ == "__main__":
    unittest.main()
