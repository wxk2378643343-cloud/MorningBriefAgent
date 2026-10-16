import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from core.application.local_api import create_local_server
from storage.sqlite import initialize
from storage.workspace import OBSIDIAN_LAYOUT, WORKSPACE_DIRECTORIES, default_workspace_root, initialize_workspace
from storage.usage import record_usage


class DesktopWorkspaceTests(unittest.TestCase):
    def test_workspace_initialization_creates_local_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            root = Path(temp_dir) / "workspace"
            info = initialize_workspace(root, database_path=database)
            self.assertTrue(info["configured"])
            self.assertEqual(info["default_root_path"], str(default_workspace_root()))
            self.assertEqual(len(info["created_files"]), len(OBSIDIAN_LAYOUT))
            for directory in WORKSPACE_DIRECTORIES:
                self.assertTrue((root / directory).is_dir())
            self.assertTrue((root / "data" / "app.sqlite3").is_file())
            for relative_path in OBSIDIAN_LAYOUT:
                self.assertTrue((root / "vault" / relative_path).is_file())
            second = initialize_workspace(root, database_path=database)
            self.assertEqual(second["created_files"], [])

    def test_api_saves_profile_and_never_accepts_secret_as_database_setting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            initialize(database)
            root = Path(temp_dir) / "workspace"
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                self._post(base + "/api/v1/workspace/initialize", {"root_path": str(root)})
                with patch("core.application.local_api.set_secret") as set_secret:
                    response = self._post(
                        base + "/api/v1/providers/deepseek/credentials",
                        {"api_key": "secret-value"},
                    )
                    self.assertTrue(response["configured"])
                    set_secret.assert_called_once()
                self._post(base + "/api/v1/profile", {"我的工作": "软件开发"})
                self.assertTrue((root / "vault" / "个人上下文.md").is_file())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_provider_and_channel_tests_only_report_credential_presence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            initialize(database)
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with patch("core.application.local_api.get_secret", side_effect=lambda name: "configured" if any(token in name for token in ("app_id", "app_secret", "api_key")) else None):
                    self.assertTrue(self._post(base + "/api/v1/providers/deepseek/test", {})["ok"])
                    self.assertTrue(self._post(base + "/api/v1/channels/feishu/test", {})["ok"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_empty_provider_and_channel_credentials_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            initialize(database)
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with self.assertRaises(Exception):
                    self._post(base + "/api/v1/providers/deepseek/credentials", {})
                with self.assertRaises(Exception):
                    self._post(base + "/api/v1/channels/feishu/credentials", {})
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_incomplete_channel_request_does_not_write_partial_credentials(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            initialize(database)
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with patch("core.application.local_api.set_secret") as set_secret:
                    with self.assertRaises(Exception):
                        self._post(
                            base + "/api/v1/channels/feishu/credentials",
                            {
                                "app_id": "app-id",
                                "app_secret": "secret",
                                "user_open_id": "user-id",
                            },
                        )
                    set_secret.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_channel_credential_store_failure_returns_safe_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            initialize(database)
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with patch(
                    "core.application.local_api.set_secret",
                    side_effect=RuntimeError("system_credential_store_unavailable"),
                ):
                    with self.assertRaises(HTTPError) as raised:
                        self._post(
                            base + "/api/v1/channels/feishu/credentials",
                            {
                                "app_id": "app-id",
                                "app_secret": "secret-value",
                                "user_open_id": "user-id",
                                "chat_id": "chat-id",
                            },
                        )
                payload = json.loads(raised.exception.read().decode("utf-8"))
                self.assertEqual(payload["error"], "credential_save_failed")
                self.assertEqual(payload["message"], "system_credential_store_unavailable")
                self.assertNotIn("secret-value", json.dumps(payload))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_workspace_source_is_selected_instead_of_project_demo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            root = Path(temp_dir) / "workspace"
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                initialized = self._post(
                    base + "/api/v1/workspace/initialize",
                    {"root_path": str(root)},
                )
                payload = self._get(base + "/api/v1/data-sources")
                self.assertEqual(payload["active_source_id"], initialized["source_id"])
                self.assertEqual(len(payload["sources"]), 1)
                self.assertEqual(
                    Path(payload["sources"][0]["root_path"]),
                    root / "vault",
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_onboarding_step_requires_real_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            initialize(database)
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with self.assertRaises(Exception):
                    self._post(
                        base + "/api/v1/onboarding/complete",
                        {"step_key": "workspace"},
                    )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_agent_status_returns_latest_usage_without_exposing_secrets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            initialize(database)
            record_usage(
                task="desktop-test",
                provider="deepseek",
                input_tokens=4,
                output_tokens=6,
                duration_ms=12,
                database_path=database,
            )
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = self._get(f"http://127.0.0.1:{server.server_port}/api/v1/agent/status")
                self.assertEqual(payload["latest"]["total_tokens"], 10)
                self.assertNotIn("api_key", json.dumps(payload))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    @staticmethod
    def _get(url):
        with urlopen(url) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _post(url, payload):
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
