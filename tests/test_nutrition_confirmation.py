"""Tests for displaying and confirming pending meal estimates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.lifestyle.nutrition_analysis import handle_confirmation
from storage.facts import record_lifestyle_fact
from storage.lifestyle import save_meal_estimate, get_meal


class NutritionConfirmationTests(unittest.TestCase):
    def test_latest_pending_meal_can_be_confirmed_by_explicit_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "facts.sqlite3")
            fact_id = record_lifestyle_fact(
                message_id="meal-confirm-1",
                category="午餐",
                text="鸡胸肉和米饭",
                database_path=database,
            )
            save_meal_estimate(fact_id, calories=600, database_path=database)
            response = handle_confirmation(
                "确认热量 650", actor="ou-user", database_path=database
            )
            meal = get_meal(fact_id, database_path=database)

        self.assertIn("650 kcal", response)
        self.assertEqual(meal["calories_confirmed"], 650)
        self.assertEqual(meal["confirmation_status"], "confirmed")
