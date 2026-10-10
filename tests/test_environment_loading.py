import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

from app.config import backend_env_path, load_environment
from app.api import google_calendar_api


class EnvironmentLoadingTests(unittest.TestCase):
    def test_backend_env_path_is_resolved_from_backend_package(self):
        expected = Path(__file__).resolve().parents[1] / "backend" / ".env"
        self.assertEqual(backend_env_path(), expected)

    def test_loader_reads_env_file_without_printing_or_returning_values(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(
                "OPSAGENT_ENV_TEST=loaded-from-file\nOPSAGENT_TEST_SECRET=fixture-only-value\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                output = StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    loaded = load_environment(env_file)
                self.assertTrue(loaded)
                self.assertEqual(os.environ.get("OPSAGENT_ENV_TEST"), "loaded-from-file")
                self.assertEqual(os.environ.get("OPSAGENT_TEST_SECRET"), "fixture-only-value")
                self.assertEqual(output.getvalue(), "")

    def test_default_loader_uses_the_resolved_backend_env_path(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("OPSAGENT_DEFAULT_PATH_TEST=backend-file\n", encoding="utf-8")
            with patch("app.config.backend_env_path", return_value=env_file), \
                 patch.dict(os.environ, {}, clear=True):
                self.assertTrue(load_environment())
                self.assertEqual(os.environ.get("OPSAGENT_DEFAULT_PATH_TEST"), "backend-file")

    def test_existing_process_environment_value_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("OPSAGENT_ENV_TEST=file-value\n", encoding="utf-8")
            with patch.dict(os.environ, {"OPSAGENT_ENV_TEST": "process-value"}):
                load_environment(env_file)
                self.assertEqual(os.environ["OPSAGENT_ENV_TEST"], "process-value")

    def test_oauth_endpoint_loads_configuration_lazily_after_app_import(self):
        class FakeFlow:
            client_config_keys = None

            @classmethod
            def from_client_config(cls, client_config, scopes, state=None):
                cls.client_config_keys = set(client_config["web"])
                return cls()

            def authorization_url(self, **_kwargs):
                return "https://accounts.google.test/authorize", "regression-state"

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(
                "GOOGLE_CLIENT_ID=fixture-client-id\n"
                "GOOGLE_CLIENT_SECRET=fixture-client-secret\n"
                "GOOGLE_REDIRECT_URI=http://127.0.0.1/callback\n",
                encoding="utf-8",
            )
            fake_package = types.ModuleType("google_auth_oauthlib")
            fake_package.__path__ = []
            fake_flow_module = types.ModuleType("google_auth_oauthlib.flow")
            fake_flow_module.Flow = FakeFlow
            fake_package.flow = fake_flow_module
            with patch("app.config.backend_env_path", return_value=env_file), \
                 patch.dict(os.environ, {}, clear=True), \
                 patch.dict(sys.modules, {
                     "google_auth_oauthlib": fake_package,
                     "google_auth_oauthlib.flow": fake_flow_module,
                 }):
                response = google_calendar_api.connect_google_calendar()
                self.assertEqual(response.status_code, 302)
                self.assertEqual(FakeFlow.client_config_keys, {
                    "client_id", "client_secret", "auth_uri", "token_uri", "redirect_uris",
                })
                self.assertTrue(os.environ.get("GOOGLE_CLIENT_ID"))
                self.assertTrue(os.environ.get("GOOGLE_CLIENT_SECRET"))
                self.assertEqual(
                    os.environ.get("GOOGLE_REDIRECT_URI"),
                    "http://127.0.0.1/callback",
                )

    def test_blank_process_variables_are_filled_from_backend_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("OPSAGENT_EMPTY_TEST=from-file\n", encoding="utf-8")
            with patch.dict(os.environ, {"OPSAGENT_EMPTY_TEST": ""}):
                load_environment(env_file)
                self.assertEqual(os.environ["OPSAGENT_EMPTY_TEST"], "from-file")


if __name__ == "__main__":
    unittest.main()
