"""Pure presentation adapter for news reports."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from core.pipeline import QualityReport


@dataclass(frozen=True)
class NewsReport:
    news_data: dict[str, Any]
    tech_items: list[dict[str, Any]]
    takeaway: str
    quality: QualityReport | None = None
    generated_at: datetime.datetime | None = None


def build_feishu_card(report: NewsReport) -> dict[str, Any]:
    generated_at = report.generated_at or datetime.datetime.now()
    news_data = report.news_data
    domestic = []
    for index, item in enumerate(news_data.get("domestic", []), 1):
        title = (
            f"[{item['title']}]({item['link']})"
            if item.get("link") else item["title"]
        )
        domestic.append(
            f"**{index}. {title}**\n"
            f"   ▸ {item.get('desc') or '来源未提供摘要'}"
        )
    world = []
    for index, item in enumerate(news_data.get("world", []), 1):
        title = (
            f"[{item['title']}]({item['link']})"
            if item.get("link") else item["title"]
        )
        world.append(
            f"**{index}. 🌍 {title}**\n"
            f"   ▸ **外媒原题**：{item.get('en_title', '')}\n"
            f"   ▸ **中文精读**：{item.get('desc') or '来源未提供摘要'}"
        )
    technology = [
        f"• 🔥 **[{item['name']}]({item['url']})**\n"
        f"   ▸ 来源：{item.get('repo') or item.get('source_url') or '公开信源'}"
        for item in report.tech_items
    ]
    sections = (
        ("【🇨🇳 国内宏观政经焦点】", domestic, "国内"),
        ("【🌍 国际一手动态】", world, "国际"),
        ("【⚡ 全球技术动态】", technology, "技术"),
    )
    elements: list[dict[str, Any]] = [{
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": (
                f"📅 **汇聚时间**：{generated_at:%Y年%m月%d日 %H:%M}\n"
                f"📡 **信源状态**："
                f"{report.quality.status_text() if report.quality else '已完成采集'}"
            ),
        },
    }]
    for title, lines, label in sections:
        elements.extend([
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{title}**\n\n"
                        + ("\n\n".join(lines) or f"⚠️ 本轮无通过校验的{label}内容")
                    ),
                },
            },
        ])
    elements.extend([
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"💡 **今日晨读结论**：\n{report.takeaway}",
            },
        },
        {
            "tag": "note",
            "elements": [{
                "tag": "plain_text",
                "content": "仅展示通过发布时间、去重和来源校验的公开信息。",
            }],
        },
    ])
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "🌍 全球大势与硬核科技雷达 · 晨报",
                },
                "template": "blue",
            },
            "elements": elements,
        },
    }
