import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from core.application.local_api import create_local_server
from storage.planning import (
    save_schedule,
    save_todo,
    list_schedules,
    list_audit_logs,
    parse_audit_time,
)
from storage.sqlite import initialize, connect


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

            save_schedule(title="今天下午会议", source_id="test_src", start_at="2026-10-22T15:00:00", end_at="2026-10-22T16:00:00", database_path=database)
            save_schedule(title="明天零点启动", source_id="test_src", start_at="2026-10-23T00:00:00", end_at="2026-10-23T01:00:00", database_path=database)

            today_schedules = list_schedules(start_date="2026-10-22T00:00:00", end_date="2026-10-23T00:00:00", database_path=database)
            titles = [s["title"] for s in today_schedules]
            self.assertIn("今天下午会议", titles)
            self.assertNotIn("明天零点启动", titles)

    def test_audit_log_timezone_strict_validation(self):
        # 1. Valid inputs: Z, positive offset (+08:00), negative offset (-05:00), with millis
        self.assertEqual(parse_audit_time("2026-10-20T16:00:00Z"), "2026-10-20 16:00:00")
        self.assertEqual(parse_audit_time("2026-10-20T16:00:00.123Z"), "2026-10-20 16:00:00")
        self.assertEqual(parse_audit_time("2026-10-21T00:00:00+08:00"), "2026-10-20 16:00:00")
        self.assertEqual(parse_audit_time("2026-10-20T11:00:00-05:00"), "2026-10-20 16:00:00")

        # 2. Reject inputs without timezone indicator -> raises ValueError('invalid_time_range')
        with self.assertRaises(ValueError):
            parse_audit_time("2026-10-21 00:00:00")

        with self.assertRaises(ValueError):
            parse_audit_time("2026-10-21T00:00:00")

        with self.assertRaises(ValueError):
            parse_audit_time("not-a-valid-date")

        # 3. HTTP API level returns 400 for invalid/no timezone range
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "server.sqlite3"
            initialize(database)
            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                # Query with no timezone -> 400
                with self.assertRaises(HTTPError) as ctx:
                    self._get(f"{base}/api/v1/audit-logs?start_time=2026-10-21%2000:00:00")
                self.assertEqual(ctx.exception.code, 400)

                # Query with valid ISO UTC -> 200
                res = self._get(f"{base}/api/v1/audit-logs?start_time=2026-10-20T16:00:00Z")
                self.assertIn("logs", res)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_audit_log_cst_midnight_boundary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "test.sqlite3"
            initialize(database)

            # Insert raw audit logs with specific created_at UTC timestamps
            with connect(database) as conn:
                # Local CST 2026-10-21 01:00:00 -> UTC 2026-10-20 17:00:00
                conn.execute(
                    "INSERT INTO audit_log (entity_type, entity_id, action, actor, created_at) VALUES ('todo', 't1', 'cst_early_morning', 'test', '2026-10-20 17:00:00')"
                )
                # Local CST 2026-10-21 23:59:59 -> UTC 2026-10-21 15:59:59
                conn.execute(
                    "INSERT INTO audit_log (entity_type, entity_id, action, actor, created_at) VALUES ('todo', 't2', 'cst_late_night', 'test', '2026-10-21 15:59:59')"
                )
                # Local CST 2026-10-22 00:00:00 -> UTC 2026-10-21 16:00:00 (Next day midnight, strictly excluded)
                conn.execute(
                    "INSERT INTO audit_log (entity_type, entity_id, action, actor, created_at) VALUES ('todo', 't3', 'cst_next_day_midnight', 'test', '2026-10-21 16:00:00')"
                )
                # Previous day CST 2026-10-20 23:59:59 -> UTC 2026-10-20 15:59:59 (Previous day, excluded)
                conn.execute(
                    "INSERT INTO audit_log (entity_type, entity_id, action, actor, created_at) VALUES ('todo', 't4', 'cst_prev_day', 'test', '2026-10-20 15:59:59')"
                )

            # Query for CST today: [2026-10-21T00:00:00+08:00, 2026-10-22T00:00:00+08:00)
            logs = list_audit_logs(
                start_time="2026-10-21T00:00:00+08:00",
                end_time="2026-10-22T00:00:00+08:00",
                database_path=database,
            )
            actions = [l["action"] for l in logs]
            self.assertIn("cst_early_morning", actions)
            self.assertIn("cst_late_night", actions)
            self.assertNotIn("cst_next_day_midnight", actions)
            self.assertNotIn("cst_prev_day", actions)


if __name__ == "__main__":
    unittest.main()
