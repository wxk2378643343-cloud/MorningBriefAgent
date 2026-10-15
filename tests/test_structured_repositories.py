"""Tests for planning, schedule, market and news repositories."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from storage.facts import record_lifestyle_fact
from storage.market import save_fund_snapshot, save_news_item
from storage.planning import list_open_todos, save_schedule, save_todo


class StructuredRepositoryTests(unittest.TestCase):
    def test_todo_and_schedule_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "app.sqlite3")
            source_id = "feishu:planning-1"
            todo_id = save_todo(
                title="确认排期",
                source_id=source_id,
                due_date="2026-10-16",
                database_path=database,
            )
            same_id = save_todo(
                title="确认排期",
                source_id=source_id,
                due_date="2026-10-16",
                status="completed",
                database_path=database,
            )
            schedule_id = save_schedule(
                title="深度工作",
                source_id=source_id,
                start_at="2026-10-16T09:00:00+08:00",
                end_at="2026-10-16T10:00:00+08:00",
                database_path=database,
            )
            open_todos = list_open_todos(
                due_date="2026-10-16", database_path=database
            )

        self.assertEqual(todo_id, same_id)
        self.assertTrue(schedule_id.startswith("schedule:"))
        self.assertEqual(open_todos, [])

    def test_market_and_news_keep_source_and_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "app.sqlite3")
            snapshot_id = save_fund_snapshot(
                fund_code="000001",
                price=1.234,
                change_percent=0.5,
                market_time="2026-10-15T14:00:00+08:00",
                data_source="market-api",
                is_realtime=True,
                database_path=database,
            )
            news_id = save_news_item(
                title="公开新闻",
                source_id="rss:1",
                category="world",
                url="https://example.test/news",
                published_at="2026-10-15T08:00:00Z",
                summary="摘要",
                database_path=database,
            )

        self.assertGreater(snapshot_id, 0)
        self.assertTrue(news_id.startswith("news:"))


if __name__ == "__main__":
    unittest.main()
