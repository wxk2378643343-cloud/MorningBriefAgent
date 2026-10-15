"""Tests for usage accounting and projection status tracking."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.agent import provider
from services.knowledge.projector import project_plan
from storage.sqlite import connect
from storage.usage import usage_summary
from server.message_processor import _append_usage_footer


class UsageAndProjectionTests(unittest.TestCase):
    def test_provider_records_estimated_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "app.sqlite3")
            with mock.patch.object(provider, "record_usage") as record, \
                    mock.patch.object(provider.agy_bridge, "ask_native_agy",
                                       return_value="回答"):
                provider.ask_text("demo-task", "abcd", "efgh")
            record.assert_called_once()
            self.assertEqual(record.call_args.kwargs["provider"], "agy")
            self.assertEqual(record.call_args.kwargs["input_tokens"], 2)

    def test_projection_is_recorded_and_upserted(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "app.sqlite3")
            with mock.patch("services.knowledge.projector.config.SQLITE_DATABASE_PATH",
                            database), \
                    mock.patch("services.knowledge.projector.config.TODO_MARKDOWN_PATH", ""), \
                    mock.patch("services.knowledge.projector.config.SCHEDULE_MARKDOWN_PATH", ""):
                project_plan({"date": "2026-10-16", "todos": ["A"]},
                             vault_root=tmp)
                project_plan({"date": "2026-10-16", "todos": ["B"]},
                             vault_root=tmp)
            with connect(database) as connection:
                rows = connection.execute(
                    "SELECT projection_key, status FROM projection_records "
                    "ORDER BY projection_key"
                ).fetchall()
            self.assertEqual([dict(row) for row in rows], [
                {"projection_key": "schedule", "status": "success"},
                {"projection_key": "todo", "status": "success"},
            ])

    def test_usage_summary_is_numeric(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "app.sqlite3")
            from storage.usage import record_usage
            record_usage(task="x", provider="mock", input_tokens=3,
                         output_tokens=4, database_path=database)
            self.assertEqual(usage_summary(database_path=database)["total_tokens"], 7)

    def test_reply_footer_is_small_and_only_added_after_agent_usage(self):
        with mock.patch(
            "server.message_processor.get_last_usage",
            return_value={
                "provider": "agy",
                "input_tokens": 10,
                "output_tokens": 4,
                "total_tokens": 14,
                "token_source": "estimated",
            },
        ):
            reply = _append_usage_footer("完成了")
        self.assertIn("<sub>Token：估算输入 10 · 输出 4 · 合计 14 · agy</sub>", reply)
