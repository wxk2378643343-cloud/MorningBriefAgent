import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from core.application.local_api import create_local_server
from storage.planning import list_all_todos
from storage.sqlite import initialize
from storage.workspace import initialize_workspace


class WorkspaceDatabaseBindingTests(unittest.TestCase):
    def _post(self, url: str, body: dict) -> dict:
        req = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, url: str) -> dict:
        with urlopen(url) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_todos_and_schedules_write_to_workspace_database(self):
        with tempfile.TemporaryDirectory() as server_dir, tempfile.TemporaryDirectory() as user_ws_dir:
            server_db = Path(server_dir) / "server.sqlite3"
            initialize(server_db)

            # Initialize workspace into user_ws_dir, passing server_db as metadata
            ws_info = initialize_workspace(user_ws_dir, database_path=server_db)
            ws_db = Path(ws_info["database_path"])
            self.assertTrue(ws_db.is_file(), f"Workspace db should exist at {ws_db}")

            # Start local API server pointing to server_db
            server = create_local_server(database_path=server_db)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                # 1. Create todo via API
                res = self._post(f"{base}/api/v1/todos", {
                    "title": "写入工作区数据库的事项",
                    "due_date": "2026-10-22",
                })
                self.assertTrue(res["ok"])

                # 2. Query workspace db directly
                ws_todos = list_all_todos(database_path=ws_db)
                self.assertEqual(len(ws_todos), 1)
                self.assertEqual(ws_todos[0]["title"], "写入工作区数据库的事项")

                # 3. Verify server_db does NOT contain this todo
                server_todos = list_all_todos(database_path=server_db)
                self.assertEqual(len(server_todos), 0, "Server metadata DB should not contain workspace todos")

                # 4. Create schedule via API
                sched_res = self._post(f"{base}/api/v1/schedules", {
                    "title": "工作区专属日程",
                    "start_at": "2026-10-22T10:00:00",
                    "end_at": "2026-10-22T11:00:00",
                })
                self.assertTrue(sched_res["ok"])

                # Check schedule in workspace db vs server db
                from storage.planning import list_schedules
                self.assertEqual(len(list_schedules(database_path=ws_db)), 1)
                self.assertEqual(len(list_schedules(database_path=server_db)), 0)

            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
