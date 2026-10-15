"""Tests for source-backed SQLite lifestyle facts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from storage.facts import get_fact, record_lifestyle_fact


class FactStorageTests(unittest.TestCase):
    def test_lifestyle_fact_is_source_backed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "facts.sqlite3")
            first = record_lifestyle_fact(
                message_id="om-meal-1",
                category="早餐",
                text="今天早餐：鸡蛋和牛奶",
                image_paths=["meal.jpg"],
                database_path=database,
            )
            second = record_lifestyle_fact(
                message_id="om-meal-1",
                category="早餐",
                text="今天早餐：鸡蛋和牛奶",
                image_paths=["meal.jpg"],
                database_path=database,
            )
            fact = get_fact(first, database_path=database)

        self.assertEqual(first, second)
        self.assertIsNotNone(fact)
        self.assertEqual(fact["source_id"], "feishu:om-meal-1")
        self.assertEqual(fact["payload"]["estimated"], False)
        self.assertEqual(fact["payload"]["category"], "早餐")
