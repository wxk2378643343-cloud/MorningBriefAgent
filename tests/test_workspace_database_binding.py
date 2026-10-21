import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from core.application.local_api import create_local_server
from storage.planning import list_all_todos, list_schedules
from storage.sqlite import initialize
from storage.workflows import _execute
from storage.workspace import (
    active_database_path,
    initialize_workspace,
    WorkspaceDatabaseUnavailableError,
    MetadataDatabaseUnavailableError,
)
from services.planning.plan_generation import save_staged_plan


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

            ws_info = initialize_workspace(user_ws_dir, database_path=server_db)
            ws_db = Path(ws_info["database_path"])
            self.assertTrue(ws_db.is_file(), f"Workspace db should exist at {ws_db}")

            server = create_local_server(database_path=server_db)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                res = self._post(f"{base}/api/v1/todos", {
                    "title": "写入工作区数据库的事项",
                    "due_date": "2026-10-22",
                })
                self.assertTrue(res["ok"])

                ws_todos = list_all_todos(database_path=ws_db)
                self.assertEqual(len(ws_todos), 1)
                self.assertEqual(ws_todos[0]["title"], "写入工作区数据库的事项")

                server_todos = list_all_todos(database_path=server_db)
                self.assertEqual(len(server_todos), 0, "Server metadata DB should not contain workspace todos")

                sched_res = self._post(f"{base}/api/v1/schedules", {
                    "title": "工作区专属日程",
                    "start_at": "2026-10-22T10:00:00",
                    "end_at": "2026-10-22T11:00:00",
                })
                self.assertTrue(sched_res["ok"])

                self.assertEqual(len(list_schedules(database_path=ws_db)), 1)
                self.assertEqual(len(list_schedules(database_path=server_db)), 0)

            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_workflow_injects_metadata_db_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "meta.sqlite3"
            log_path = Path(temp_dir) / "test.log"
            initialize(db_path)

            mock_proc = MagicMock()
            mock_proc.wait.return_value = 0

            with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
                _execute("run123", "inspect", db_path, log_path)
                mock_popen.assert_called_once()
                _, kwargs = mock_popen.call_args
                env = kwargs.get("env", {})
                self.assertEqual(
                    env.get("MORNINGBRIEF_METADATA_DATABASE_PATH"),
                    str(db_path.resolve()),
                )

    def test_plan_generation_writes_to_workspace_db_via_metadata_context(self):
        with tempfile.TemporaryDirectory() as server_dir, tempfile.TemporaryDirectory() as user_ws_dir, tempfile.TemporaryDirectory() as plan_dir:
            server_db = Path(server_dir) / "server.sqlite3"
            initialize(server_db)
            ws_info = initialize_workspace(user_ws_dir, database_path=server_db)
            ws_db = Path(ws_info["database_path"])

            staged_path = Path(plan_dir) / "staged.json"
            plan_data = {
                "date": "2026-10-22",
                "todos": ["Agent 生成的计划待办"],
                "schedule_slots": [{
                    "name": "Agent 生成的日程",
                    "start": "09:00",
                    "end": "10:00",
                }],
            }

            # Pass metadata_database_path explicitly to save_staged_plan
            save_staged_plan(plan_data, path=staged_path, metadata_database_path=server_db)

            # Check that todo & schedule are written to ws_db, not server_db
            ws_todos = list_all_todos(database_path=ws_db)
            self.assertEqual(len(ws_todos), 1)
            self.assertEqual(ws_todos[0]["title"], "Agent 生成的计划待办")

            ws_schedules = list_schedules(database_path=ws_db)
            self.assertEqual(len(ws_schedules), 1)
            self.assertEqual(ws_schedules[0]["title"], "Agent 生成的日程")

            # server_db must be empty of these
            self.assertEqual(len(list_all_todos(database_path=server_db)), 0)
            self.assertEqual(len(list_schedules(database_path=server_db)), 0)

    def test_active_database_path_probe_and_error_hierarchy(self):
        with tempfile.TemporaryDirectory() as server_dir, tempfile.TemporaryDirectory() as user_ws_dir:
            server_db = Path(server_dir) / "server.sqlite3"
            initialize(server_db)

            # 1. Unconfigured workspace -> returns metadata database
            unconfigured_active = active_database_path(server_db)
            self.assertEqual(unconfigured_active, server_db.resolve())

            # 2. Configured workspace -> returns workspace database
            ws_info = initialize_workspace(user_ws_dir, database_path=server_db)
            ws_db = Path(ws_info["database_path"])
            self.assertEqual(active_database_path(server_db), ws_db.resolve())

            # 3. Workspace db missing -> raises WorkspaceDatabaseUnavailableError
            ws_db.unlink()
            with self.assertRaises(WorkspaceDatabaseUnavailableError):
                active_database_path(server_db)

            # 4. Workspace db corrupted / not a sqlite db -> raises WorkspaceDatabaseUnavailableError
            ws_db.write_text("corrupted content not a sqlite db", encoding="utf-8")
            with self.assertRaises(WorkspaceDatabaseUnavailableError):
                active_database_path(server_db)

            # 5. Metadata database completely invalid/corrupted -> raises MetadataDatabaseUnavailableError
            bad_meta = Path(server_dir) / "corrupt_meta.sqlite3"
            bad_meta.write_text("garbage", encoding="utf-8")
            with self.assertRaises(MetadataDatabaseUnavailableError):
                active_database_path(bad_meta)

    def test_missing_workspace_db_returns_503_for_all_endpoints(self):
        with tempfile.TemporaryDirectory() as server_dir, tempfile.TemporaryDirectory() as user_ws_dir:
            server_db = Path(server_dir) / "server.sqlite3"
            initialize(server_db)
            ws_info = initialize_workspace(user_ws_dir, database_path=server_db)
            ws_db = Path(ws_info["database_path"])

            # Delete the workspace database to simulate missing storage
            ws_db.unlink()

            server = create_local_server(database_path=server_db)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                # GET /api/v1/todos -> 503
                with self.assertRaises(HTTPError) as ctx:
                    self._get(f"{base}/api/v1/todos")
                self.assertEqual(ctx.exception.code, 503)

                # GET /api/v1/schedules -> 503
                with self.assertRaises(HTTPError) as ctx:
                    self._get(f"{base}/api/v1/schedules")
                self.assertEqual(ctx.exception.code, 503)

                # GET /api/v1/audit-logs -> 503
                with self.assertRaises(HTTPError) as ctx:
                    self._get(f"{base}/api/v1/audit-logs")
                self.assertEqual(ctx.exception.code, 503)

                # POST /api/v1/todos -> 503
                with self.assertRaises(HTTPError) as ctx:
                    self._post(f"{base}/api/v1/todos", {"title": "不能写入任何数据"})
                self.assertEqual(ctx.exception.code, 503)

                # POST /api/v1/todos/fake_id/status -> 503
                with self.assertRaises(HTTPError) as ctx:
                    self._post(f"{base}/api/v1/todos/fake_id/status", {"status": "completed"})
                self.assertEqual(ctx.exception.code, 503)

                # POST /api/v1/schedules -> 503
                with self.assertRaises(HTTPError) as ctx:
                    self._post(f"{base}/api/v1/schedules", {
                        "title": "不能写入日程",
                        "start_at": "2026-10-22T10:00:00",
                        "end_at": "2026-10-22T11:00:00",
                    })
                self.assertEqual(ctx.exception.code, 503)

                # Verify server_db has 0 todos & 0 schedules
                self.assertEqual(len(list_all_todos(database_path=server_db)), 0)
                self.assertEqual(len(list_schedules(database_path=server_db)), 0)

            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
