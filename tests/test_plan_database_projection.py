"""Verify staged plans are projected into SQLite records."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.planning import plan_generation
from storage.planning import list_open_todos


class PlanDatabaseProjectionTests(unittest.TestCase):
    def test_save_staged_plan_projects_todos_and_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_file = Path(tmp) / "plan.json"
            database = Path(tmp) / "facts.sqlite3"
            with mock.patch.object(
                plan_generation.config,
                "SQLITE_DATABASE_PATH",
                str(database),
            ):
                plan_generation.save_staged_plan(
                    {
                        "date": "2026-10-16",
                        "todos": ["确认排期"],
                        "schedule_slots": [{
                            "name": "深度工作",
                            "start": "09:00",
                            "end": "10:00",
                            "summary": "项目推进",
                        }],
                    },
                    plan_file,
                )
            todos = list_open_todos(
                due_date="2026-10-16", database_path=str(database)
            )

        self.assertEqual([item["title"] for item in todos], ["确认排期"])
