"""Tests for pending versus confirmed nutrition measurements."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from storage.facts import record_lifestyle_fact
from storage.lifestyle import confirm_meal, get_meal, save_meal_estimate


class LifestyleRepositoryTests(unittest.TestCase):
    def test_estimate_is_pending_until_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "facts.sqlite3")
            fact_id = record_lifestyle_fact(
                message_id="meal-1",
                category="早餐",
                text="鸡蛋和牛奶",
                database_path=database,
            )
            save_meal_estimate(fact_id, calories=420, protein=25, database_path=database)
            pending = get_meal(fact_id, database_path=database)
            self.assertEqual(pending["calories_estimated"], 420)
            self.assertIsNone(pending["calories_confirmed"])
            self.assertEqual(pending["confirmation_status"], "pending")

            self.assertTrue(confirm_meal(
                fact_id, calories=450, actor="user", database_path=database
            ))
            confirmed = get_meal(fact_id, database_path=database)

        self.assertEqual(confirmed["calories_confirmed"], 450)
        self.assertEqual(confirmed["confirmation_status"], "confirmed")


if __name__ == "__main__":
    unittest.main()
