import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from core.application.local_api import create_local_server
from storage.planning import save_schedule, save_todo, list_schedules, list_audit_logs
from storage.sqlite import initialize
from storage.workspace import initialize_workspace


class TodoScheduleApiTests(unittest.TestCase):
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

    def test_todos_and_schedules_crud(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            initialize(database)
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                # 1. Create todo
                create_res = self._post(f"{base}/api/v1/todos", {
                    "title": "测试待办1",
                    "due_date": "2026-10-22",
                    "priority": "high",
                })
                self.assertTrue(create_res["ok"])
                todo_id = create_res["id"]

                # 2. List todos
                list_res = self._get(f"{base}/api/v1/todos")
                self.assertEqual(len(list_res["todos"]), 1)
                self.assertEqual(list_res["todos"][0]["title"], "测试待办1")
                self.assertEqual(list_res["todos"][0]["status"], "open")

                # 3. Reject invalid status (e.g. banana)
                with self.assertRaises(HTTPError) as ctx:
                    self._post(f"{base}/api/v1/todos/{todo_id}/status", {"status": "banana"})
                self.assertEqual(ctx.exception.code, 400)

                # 4. Update status to completed, cancelled, postponed
                status_res = self._post(f"{base}/api/v1/todos/{todo_id}/status", {
                    "status": "completed"
                })
                self.assertTrue(status_res["ok"])

                # 5. Check completed
                list_res2 = self._get(f"{base}/api/v1/todos?status=completed")
                self.assertEqual(len(list_res2["todos"]), 1)
                self.assertIsNotNone(list_res2["todos"][0]["completed_at"])

                # 6. Postpone todo
                postpone_res = self._post(f"{base}/api/v1/todos/{todo_id}/status", {
                    "status": "postponed"
                })
                self.assertTrue(postpone_res["ok"])

                # 7. Check audit logs
                audit_res = self._get(f"{base}/api/v1/audit-logs?entity_type=todo")
                self.assertGreaterEqual(len(audit_res["logs"]), 3)
                actions = [item["action"] for item in audit_res["logs"]]
                self.assertIn("create", actions)
                self.assertIn("status_change_to_completed", actions)
                self.assertIn("status_change_to_postponed", actions)

                # 8. Create schedule
                sched_res = self._post(f"{base}/api/v1/schedules", {
                    "title": "评审会议",
                    "start_at": "2026-10-22T14:00:00",
                    "end_at": "2026-10-22T15:00:00",
                })
                self.assertTrue(sched_res["ok"])

                # 9. List schedules
                sched_list = self._get(f"{base}/api/v1/schedules")
                self.assertEqual(len(sched_list["schedules"]), 1)
                self.assertEqual(sched_list["schedules"][0]["title"], "评审会议")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_idempotent_save_does_not_duplicate_audit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "test.sqlite3"
            initialize(database)

            # 1. Save todo twice with same params
            id1 = save_todo(title="重复保存待办", source_id="test_src", due_date="2026-10-22", database_path=database)
            id2 = save_todo(title="重复保存待办", source_id="test_src", due_date="2026-10-22", database_path=database)
            self.assertEqual(id1, id2)

            logs = list_audit_logs(entity_type="todo", database_path=database)
            # Only one 'create' audit log should exist
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["action"], "create")

            # Update priority -> should record 'update'
            save_todo(title="重复保存待办", source_id="test_src", due_date="2026-10-22", priority="high", database_path=database)
            logs_after = list_audit_logs(entity_type="todo", database_path=database)
            self.assertEqual(len(logs_after), 2)
            self.assertEqual(logs_after[0]["action"], "update")

            # 2. Save schedule twice with same params
            sid1 = save_schedule(title="晨会", source_id="test_src", start_at="2026-10-22T09:00:00", end_at="2026-10-22T09:30:00", database_path=database)
            sid2 = save_schedule(title="晨会", source_id="test_src", start_at="2026-10-22T09:00:00", end_at="2026-10-22T09:30:00", database_path=database)
            self.assertEqual(sid1, sid2)

            slogs = list_audit_logs(entity_type="schedule", database_path=database)
            self.assertEqual(len(slogs), 1)
            self.assertEqual(slogs[0]["action"], "create")

    def test_schedule_half_open_interval_excludes_midnight_next_day(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "test.sqlite3"
            initialize(database)

            # Schedule today
            save_schedule(title="今天下午会议", source_id="test_src", start_at="2026-10-22T15:00:00", end_at="2026-10-22T16:00:00", database_path=database)
            # Schedule exactly at tomorrow midnight 00:00:00
            save_schedule(title="明天零点启动", source_id="test_src", start_at="2026-10-23T00:00:00", end_at="2026-10-23T01:00:00", database_path=database)

            # Query for [2026-10-22, 2026-10-23)
            today_schedules = list_schedules(start_date="2026-10-22T00:00:00", end_date="2026-10-23T00:00:00", database_path=database)
            titles = [s["title"] for s in today_schedules]
            self.assertIn("今天下午会议", titles)
            self.assertNotIn("明天零点启动", titles)


if __name__ == "__main__":
    unittest.main()
