import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from core.application.local_api import create_local_server
from storage.sqlite import initialize
from storage.workspace import WORKSPACE_DIRECTORIES, initialize_workspace


class DesktopWorkspaceTests(unittest.TestCase):
    def test_workspace_initialization_creates_local_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            root = Path(temp_dir) / "workspace"
            info = initialize_workspace(root, database_path=database)
            self.assertTrue(info["configured"])
            for directory in WORKSPACE_DIRECTORIES:
                self.assertTrue((root / directory).is_dir())
            self.assertTrue((root / "data" / "app.sqlite3").is_file())

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
