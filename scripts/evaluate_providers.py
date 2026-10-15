"""Compare AGY and DeepSeek on fixed, non-personal evaluation cases."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from core.agent.deepseek_provider import DeepSeekProvider
from core.agent.evaluation import EvaluationCase, evaluate_provider, compare_results
from core.agent import provider as agy_provider
from storage.usage import record_usage


CASES = [
    EvaluationCase(
        "todo-1", "daily-plan",
        '只返回 JSON：{"todos":["整理项目文档"],"schedule_slots":[]}。'
        "用户说：明天上午安排我整理项目文档。",
        ("todos", "schedule_slots"),
    ),
    EvaluationCase(
        "news-1", "news",
        '只返回 JSON：{"title":"标题","source":"来源","summary":"摘要"}。'
        "分析一条新闻：某公司发布了新的开源数据库。",
        ("title", "source", "summary"),
    ),
    EvaluationCase(
        "meal-1", "meal",
        '只返回 JSON：{"calories_estimated":数字,"protein_estimated":数字}。'
        "估算一份鸡胸肉、米饭和西兰花午餐。",
        ("calories_estimated", "protein_estimated"),
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deepseek-key", default=os.getenv("DEEPSEEK_API_KEY", ""))
    args = parser.parse_args()
    if not args.deepseek_key:
        parser.error("请配置 DEEPSEEK_API_KEY")

    deepseek = DeepSeekProvider(
        args.deepseek_key,
        endpoint=os.getenv(
            "DEEPSEEK_API_URL",
            "https://api.deepseek.com/v1/chat/completions",
        ),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    )

    deepseek_results = []
    for case in CASES:
        response = deepseek.ask_json(case.prompt)
        valid = isinstance(response.value, dict) and all(
            key in response.value for key in case.expected_keys
        )
        deepseek_results.append({
            "provider": "deepseek",
            "case_id": case.case_id,
            "success": valid,
            "schema_valid": valid,
            "duration_ms": response.duration_ms,
        })
        record_usage(
            task=f"evaluation-{case.case_id}",
            provider="deepseek",
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            token_source="actual",
            duration_ms=response.duration_ms,
            status="success" if valid else "invalid",
        )

    agy_results = evaluate_provider(
        "agy", CASES,
        lambda case: agy_provider.ask_json(case.task, case.prompt),
    )
    summary = compare_results(
        [type("Result", (), result)() for result in deepseek_results],
        agy_results,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
