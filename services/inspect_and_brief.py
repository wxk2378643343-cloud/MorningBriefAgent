#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent-first daily brief.

The service gathers configured local context and recent email metadata, then
lets the local agent decide what is relevant. No subject, schedule, exam,
fitness or career plan is embedded in source code.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(PROJECT_ROOT), str(PROJECT_ROOT / "core")]

import agent_context
import agy_bridge
import config
from email_analyzer import get_latest_high_value_email_digest
from feishu_client import feishu_client


def collect_brief_data() -> Dict[str, Any]:
    """Collect only configured context and email summaries."""
    email_data = get_latest_high_value_email_digest(config.VAULT_ROOT)
    context = agent_context.collect_context("daily brief", max_files=10)
    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "context": context,
        "emails": email_data,
    }


def analyze_brief(data: Dict[str, Any]) -> str:
    """Ask the local agent to prioritize and explain the daily brief."""
    email_text = json.dumps(data.get("emails", []), ensure_ascii=False, indent=2)
    prompt = agent_context.build_prompt(
        task=(
            "生成一份简洁的每日简报。只总结资料中确实出现的事项，区分事实、"
            "推断和建议；给出最多三项下一步行动。不要凭空添加固定作息、学科、"
            "运动、投资或职业目标。"
        ),
        query="请分析今天最值得关注的事项。",
        context=f"{data.get('context', '')}\n\n【邮件摘要】\n{email_text}",
    )
    try:
        result = agy_bridge.ask_native_agy("daily-brief", prompt)
        if result and not result.startswith("❌"):
            return result
    except Exception:
        pass
    if data.get("emails"):
        return "\n".join(
            f"• {item.get('subject', '未命名邮件')}" for item in data["emails"]
        )
    return "暂无足够的本地资料生成简报，请先配置 AGENT_CONTEXT_FILES 或 AGENT_CONTEXT_DIRS。"


def build_detailed_feishu_card(analysis: str) -> Dict[str, Any]:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "🧭 每日知识库简报"},
        },
        "elements": [
            {"tag": "markdown", "content": analysis},
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "内容来自本地配置上下文与可用邮件摘要。",
                    }
                ],
            },
        ],
    }


def send_feishu_card(card: Dict[str, Any]) -> bool:
    return feishu_client.send_card(card)


def record_detailed_to_obsidian(analysis: str, generated_at: str) -> str | None:
    """Archive the result only when an output directory is configured."""
    output_dir = os.getenv("BRIEF_OUTPUT_DIR", "")
    if not output_dir:
        return None
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{generated_at[:10]}-daily-brief.md"
    path.write_text(
        f"---\ncreated: {generated_at}\ntags: [daily-brief, agent]\n---\n\n"
        f"# Daily Brief ({generated_at[:10]})\n\n{analysis}\n",
        encoding="utf-8",
    )
    return str(path)


def main() -> None:
    data = collect_brief_data()
    analysis = analyze_brief(data)
    card = build_detailed_feishu_card(analysis)
    if not send_feishu_card(card):
        print(analysis)
    record_detailed_to_obsidian(analysis, data["generated_at"])


if __name__ == "__main__":
    main()
