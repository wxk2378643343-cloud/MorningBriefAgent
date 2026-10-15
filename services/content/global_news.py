#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Global news workflow façade: collect -> validate -> analyze -> publish."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from core.integrations.feishu.gateway import feishu_gateway
from core.integrations.feishu.idempotency import make_key
from core.pipeline import QualityReport, SourceStatus
from core.runtime import config
from services.content import news_analysis, news_renderer, news_sources
from storage.market import save_news_item


LOCAL_PROXY = config.LOCAL_PROXY
DEFAULT_DOMESTIC_URLS = (
    "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=8&page=1",
    "https://zhibo.sina.com.cn/api/zhibo/feed?zhibo_id=152&id=0&tag_id=0&page=1&page_size=6&type=0",
)
DEFAULT_WORLD_URLS = (
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
)
DEFAULT_TECH_URLS = ("https://github.blog/changelog/feed/",)
_feed_entries = news_sources.feed_entries


def _with_source_ids(
    category: str, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {**item, "source_id": str(item.get("source_id") or f"{category}:{index}")}
        for index, item in enumerate(news_sources.deduplicate(items))
    ]


def get_domestic_news(opener=None) -> list[dict[str, Any]]:
    return _with_source_ids(
        "domestic",
        news_sources.collect_domestic(
            config.NEWS_DOMESTIC_URLS or DEFAULT_DOMESTIC_URLS,
            fallback_link=config.NEWS_FALLBACK_LINK,
            opener=opener,
        ),
    )


def normalize_world_news_batch(
    source_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compatibility façade for callers and tests."""
    return news_analysis.normalize_world_news(source_items)


def get_world_news(opener=None) -> list[dict[str, Any]]:
    source_items = _with_source_ids(
        "world",
        news_sources.collect_feed_items(
            config.NEWS_WORLD_URLS or DEFAULT_WORLD_URLS,
            proxy=LOCAL_PROXY,
            opener=opener,
        ),
    )
    return normalize_world_news_batch(source_items)


def get_domestic_and_world_news() -> dict[str, list[dict[str, Any]]]:
    return {"domestic": get_domestic_news(), "world": get_world_news()}


def get_tech_radar_news(opener=None) -> list[dict[str, Any]]:
    local = news_sources.collect_local_tech(config.TECH_NEWS_DIR)
    if local:
        return _with_source_ids("technology", local)
    feed_items = news_sources.collect_feed_items(
        config.NEWS_TECH_URLS or DEFAULT_TECH_URLS,
        proxy=LOCAL_PROXY,
        opener=opener,
    )
    return _with_source_ids(
        "technology",
        [
            {
                "name": item["title"],
                "repo": "GitHub Changelog",
                "url": item["link"],
                "desc": item.get("desc", ""),
                "published": item.get("published", ""),
                "source_url": item.get("source_url", ""),
            }
            for item in feed_items
        ],
    )


def _fresh(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in news_sources.deduplicate(items)
        if news_sources.is_fresh(item)
    ]


def validate_news_inputs(
    news_data: dict[str, Any],
    tech_items: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    return (
        {
            "domestic": _fresh(list(news_data.get("domestic", []))),
            "world": _fresh(list(news_data.get("world", []))),
        },
        _fresh(list(tech_items)),
    )


def evaluate_news_quality(
    news_data: dict[str, Any],
    tech_items: list[dict[str, Any]],
) -> QualityReport:
    """Accept only fresh, timestamped and de-duplicated source items."""
    validated_news, validated_tech = validate_news_inputs(news_data, tech_items)
    statuses = []
    for label, raw, valid in (
        ("国内", news_data.get("domestic", []), validated_news["domestic"]),
        ("国际", news_data.get("world", []), validated_news["world"]),
        ("技术", tech_items, validated_tech),
    ):
        rejected = len(raw) - len(valid)
        detail = (
            f"{label}信源没有通过发布时间与去重校验"
            if not valid else (
                f"{label}信源有 {rejected} 条过期、无时间或重复内容被排除"
                if rejected else ""
            )
        )
        statuses.append(SourceStatus(label, len(valid), bool(valid), detail))
    return QualityReport.evaluate(
        statuses, minimum_total=3, minimum_healthy_sources=2
    )


def generate_news_takeaway(
    news_data: dict[str, Any],
    tech_items: list[dict[str, Any]],
) -> str:
    return news_analysis.generate_takeaway(news_data, tech_items)


def build_feishu_news_card(
    news_data: dict[str, Any],
    tech_items: list[dict[str, Any]],
    quality: QualityReport | None = None,
    *,
    takeaway: str = "",
) -> dict[str, Any]:
    """Pure card construction; Agent analysis must happen before this call."""
    return news_renderer.build_feishu_card(news_renderer.NewsReport(
        news_data=news_data,
        tech_items=tech_items,
        takeaway=takeaway or "本次未生成可回溯的晨读结论，请以原文链接为准。",
        quality=quality,
    ))


def send_feishu(card: dict[str, Any]) -> bool:
    return feishu_gateway.send_card_once(
        card, make_key("feishu-card", "news", datetime.date.today().isoformat())
    )


def record_news_to_obsidian(
    news_data: dict[str, Any], tech_items: list[dict[str, Any]]
) -> str | None:
    if not config.TECH_NEWS_DIR:
        return None
    today = datetime.date.today().isoformat()
    directory = Path(config.TECH_NEWS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{today}-全球大势与科技早报.md"
    lines = [
        "---", f'title: "{today} 全球大势与科技早报"', f"date: {today}",
        "tags: [global-news, tech-radar]", 'status: "source-validated"', "---",
        "", f"# 🌍 {today} 全球大势与科技早报", "",
    ]
    for heading, items in (
        ("国内宏观政经", news_data.get("domestic", [])),
        ("国际一手动态", news_data.get("world", [])),
    ):
        lines.extend([f"## {heading}", ""])
        lines.extend(
            f"- **[{item['title']}]({item.get('link', '')})**：{item.get('desc', '')}"
            for item in items
        )
        lines.append("")
    lines.extend(["## 技术动态", ""])
    lines.extend(
        f"- **[{item['name']}]({item.get('url', '')})**"
        for item in tech_items
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 全球早报已成功落盘至: {path}")
    return str(path)


def main() -> bool:
    print("🚀 启动全球大势与科技雷达早报流水线...")
    collected_news = get_domestic_and_world_news()
    collected_tech = get_tech_radar_news()
    quality = evaluate_news_quality(collected_news, collected_tech)
    if not quality.ready:
        print(f"⚠️ 新闻质量门禁未通过：{'；'.join(quality.issues)}")
        return False
    news_data, tech_items = validate_news_inputs(collected_news, collected_tech)
    for category, items in (
        ("domestic", news_data.get("domestic", [])),
        ("world", news_data.get("world", [])),
    ):
        for item in items:
            try:
                save_news_item(
                    title=str(item.get("title", "")),
                    source_id=str(item.get("source_id", "")),
                    category=category,
                    url=str(item.get("link", "")),
                    published_at=str(item.get("published", "")),
                    summary=str(item.get("desc", "")),
                )
            except Exception as exc:
                print(f"⚠️ 保存新闻条目失败: {exc}")
    for item in tech_items:
        try:
            save_news_item(
                title=str(item.get("name", "")),
                source_id=str(item.get("source_id", "")),
                category="technology",
                url=str(item.get("url", "")),
                published_at=str(item.get("published", "")),
                summary=str(item.get("desc", "")),
            )
        except Exception as exc:
            print(f"⚠️ 保存技术条目失败: {exc}")
    takeaway = generate_news_takeaway(news_data, tech_items)
    card = build_feishu_news_card(
        news_data, tech_items, quality, takeaway=takeaway
    )
    if not send_feishu(card):
        return False
    record_news_to_obsidian(news_data, tech_items)
    print("🎉 全球早报推送全流程顺利完成！")
    return True


if __name__ == "__main__":
    main()
