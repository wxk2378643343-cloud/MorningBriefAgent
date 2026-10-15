"""Offline comparison tests for AGY/API provider behavior."""

from __future__ import annotations

import unittest

from core.agent.evaluation import (
    EvaluationCase,
    compare_results,
    evaluate_provider,
)
from storage.usage import estimate_tokens


CASES = [
    EvaluationCase("todo-1", "daily-plan", "整理项目文档并安排明日上午时间", ("todos", "schedule_slots")),
    EvaluationCase("news-1", "news", "总结这条新闻并返回来源", ("title", "source")),
    EvaluationCase("meal-1", "meal", "识别午餐并估算热量", ("calories_estimated",)),
]


class ProviderEvaluationTests(unittest.TestCase):
    def test_same_cases_are_run_for_each_provider(self):
        def fake_provider(case):
            if case.task == "daily-plan":
                return {"todos": ["整理项目文档"], "schedule_slots": []}
            if case.task == "news":
                return {"title": "新闻", "source": "source-1"}
            return {"calories_estimated": 600}

        agy = evaluate_provider("agy", CASES, fake_provider,
                                estimate_tokens=estimate_tokens)
        api = evaluate_provider("api", CASES, fake_provider,
                                estimate_tokens=estimate_tokens)
        self.assertEqual([item.case_id for item in agy],
                         [item.case_id for item in api])
        self.assertTrue(all(item.success for item in agy + api))
        self.assertEqual(compare_results(agy, api)["agy"]["success_rate"], 1.0)

    def test_one_provider_failure_does_not_hide_other_cases(self):
        def flaky(case):
            if case.case_id == "news-1":
                raise RuntimeError("provider timeout")
            return {"todos": [], "schedule_slots": [], "calories_estimated": 1,
                    "title": "ok", "source": "s"}

        results = evaluate_provider("api", CASES, flaky)
        self.assertEqual(len(results), 3)
        self.assertFalse(results[1].success)
        self.assertEqual(results[1].error, "provider timeout")

    def test_invalid_structured_output_is_not_success(self):
        results = evaluate_provider(
            "agy", CASES, lambda _case: {"text": "看起来不错"}
        )
        self.assertEqual(sum(item.success for item in results), 0)
        self.assertEqual(compare_results(results)["agy"]["schema_valid_rate"], 0.0)
