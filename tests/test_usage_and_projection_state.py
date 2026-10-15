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
