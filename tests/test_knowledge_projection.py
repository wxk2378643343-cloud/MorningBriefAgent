"""Tests for deterministic Obsidian plan projections."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.knowledge.projector import project_plan


class KnowledgeProjectionTests(unittest.TestCase):
    def test_plan_projects_to_dedicated_markdown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(
                "services.knowledge.projector.config.TODO_MARKDOWN_PATH", ""
            ), mock.patch(
                "services.knowledge.projector.config.SCHEDULE_MARKDOWN_PATH", ""
            ):
                paths = project_plan(
                    {
                        "date": "2026-10-16",
                        "todos": ["整理项目文档"],
                        "schedule_slots": [{
                            "name": "整理项目文档",
                            "start": "09:00",
                            "end": "10:00",
                        }],
                    },
                    vault_root=tmp,
                )
            todo = Path(tmp, "03 - 待办事项", "Agent-今日待办.md")
            schedule = Path(tmp, "03 - 待办事项", "Agent-日程.md")

            self.assertEqual(len(paths), 2)
            self.assertIn("- [ ] 整理项目文档", todo.read_text(encoding="utf-8"))
            self.assertIn(
                "- 09:00–10:00 整理项目文档",
                schedule.read_text(encoding="utf-8"),
            )
