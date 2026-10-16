import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from core.application.local_api import create_local_server
from storage.onboarding import skip_step
from storage.sqlite import initialize


class LocalApplicationApiTests(unittest.TestCase):
    def test_status_discovery_and_step_completion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                status = self._get(f"{base}/api/v1/onboarding/status")
                self.assertEqual(status["current_step"], "workspace")
                discovery = self._get(f"{base}/api/v1/providers/discovery")
                self.assertIn("providers", discovery)
                self._post(
                    f"{base}/api/v1/workspace/initialize",
                    {"root_path": str(Path(temp_dir) / "workspace")},
                )
                completed = self._post(
                    f"{base}/api/v1/onboarding/complete",
                    {"step_key": "workspace", "detail": "local workspace initialized"},
                )
                self.assertEqual(completed["current_step"], "provider")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_invalid_step_returns_bad_request(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = Request(
                    f"http://127.0.0.1:{server.server_port}/api/v1/onboarding/complete",
                    data=b'{"step_key":"secrets"}',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(Exception) as caught:
                    urlopen(request)
                self.assertIn("400", str(caught.exception))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_workspace_completion_does_not_bypass_legacy_skipped_steps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            for step_key in ("provider", "channel", "profile"):
                skip_step(step_key, database_path=database)
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                self._post(
                    f"{base}/api/v1/workspace/initialize",
                    {"root_path": str(Path(temp_dir) / "workspace")},
                )
                status = self._post(
                    f"{base}/api/v1/onboarding/complete",
                    {"step_key": "workspace", "detail": "local workspace initialized"},
                )
                self.assertFalse(status["complete"])
                self.assertEqual(status["current_step"], "provider")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    @staticmethod
    def _get(url: str):
        with urlopen(url) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _post(url: str, payload: dict):
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
