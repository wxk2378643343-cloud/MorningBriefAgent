"""Tests for safe, pending-only nutrition estimates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.lifestyle import nutrition_analysis
from storage.facts import record_lifestyle_fact
from storage.lifestyle import get_meal


class NutritionAnalysisTests(unittest.TestCase):
    def test_agent_estimate_is_saved_as_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "facts.sqlite3")
            fact_id = record_lifestyle_fact(
                message_id="meal-estimate-1",
                category="午餐",
                text="米饭、鸡胸肉和蔬菜",
                database_path=database,
            )
            with mock.patch.object(
                nutrition_analysis.agent_provider,
                "ask_json",
                return_value={
                    "calories_estimated": 680,
                    "protein_estimated": 42,
                    "confidence": 0.8,
                    "basis": "按明确描述估算",
                },
            ):
                result = nutrition_analysis.estimate_meal(
                    fact_id=fact_id,
                    category="午餐",
                    text="米饭、鸡胸肉和蔬菜",
                    database_path=database,
                )
            meal = get_meal(fact_id, database_path=database)

        self.assertEqual(result["status"], "pending")
        self.assertEqual(meal["calories_estimated"], 680)
        self.assertIsNone(meal["calories_confirmed"])
        self.assertEqual(meal["confirmation_status"], "pending")

    def test_invalid_estimate_is_not_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = str(Path(tmp) / "facts.sqlite3")
            fact_id = record_lifestyle_fact(
                message_id="meal-estimate-2",
                category="早餐",
                text="不明确的早餐",
                database_path=database,
            )
            with mock.patch.object(
                nutrition_analysis.agent_provider,
                "ask_json",
                return_value={"calories_estimated": 50000},
            ):
                result = nutrition_analysis.estimate_meal(
                    fact_id=fact_id,
                    category="早餐",
                    text="不明确的早餐",
                    database_path=database,
                )
            meal = get_meal(fact_id, database_path=database)

        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(meal["calories_estimated"])
