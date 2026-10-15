"""Agent analysis for news; every generated statement retains source IDs."""

from __future__ import annotations

import json
from typing import Any

from core.agent import context as agent_context
from core.agent import provider as agent_provider
from core.pipeline import AgentBatcher


def normalize_world_news(
    source_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not source_items:
        return []
    indexed = [
        {**item, "source_id": str(item.get("source_id") or f"world:{index}")}
        for index, item in enumerate(source_items)
    ]
    output: list[dict[str, Any]] = []
    batches = AgentBatcher[dict[str, Any]](15000).partition(
        indexed, envelope=lambda values: {"items": values}
    )
    for batch_index, batch in enumerate(batches, 1):
        valid_ids = {item["source_id"] for item in batch}
        normalized: dict[str, dict[str, str]] = {}
        prompt = agent_context.build_prompt(
            task=(
                "批量翻译并压缩外文新闻。严格输出 JSON："
                "{\"items\":[{\"source_id\":\"输入ID\",\"title\":\"准确中文标题\","
                "\"summary\":\"基于原文的中文摘要\"}]}。source_id 必须来自输入；"
                "只陈述输入明确支持的事实，不补充背景、预测或立场。"
            ),
            query=f"处理国际新闻批次 {batch_index}/{len(batches)}。",
            context=json.dumps({"items": batch}, ensure_ascii=False),
        )
        try:
            result = agent_provider.ask_json("world-news-batch", prompt)
            for item in (result or {}).get("items", []):
                if not isinstance(item, dict):
                    continue
                source_id = str(item.get("source_id", ""))
                title = str(item.get("title", "")).strip()
                summary = str(item.get("summary", "")).strip()
                if source_id in valid_ids and title and summary:
                    normalized[source_id] = {"title": title, "desc": summary}
        except Exception as exc:
            print(f"⚠️ Agent 国际新闻批次 {batch_index} 暂不可用: {exc}")
        for source in batch:
            transformed = normalized.get(source["source_id"], {})
            output.append({
                **source,
                "title": transformed.get("title")
                or f"国际新闻：{str(source.get('title', ''))[:80]}",
                "en_title": source.get("title", ""),
                "desc": transformed.get("desc")
                or source.get("desc", "")
                or "原文摘要为空，请阅读来源链接。",
            })
    return output


def generate_takeaway(
    news_data: dict[str, Any],
    tech_items: list[dict[str, Any]],
) -> str:
    sources: list[dict[str, Any]] = []
    for category, items in (
        ("domestic", news_data.get("domestic", [])),
        ("world", news_data.get("world", [])),
        ("technology", tech_items),
    ):
        for index, item in enumerate(items):
            sources.append({
                "source_id": str(item.get("source_id") or f"{category}:{index}"),
                "category": category,
                "title": item.get("title") or item.get("name"),
                "summary": item.get("desc", ""),
                "published": item.get("published", ""),
            })
    claims: list[str] = []
    batches = AgentBatcher[dict[str, Any]](15000).partition(
        sources, envelope=lambda values: {"sources": values}
    )
    for batch_index, batch in enumerate(batches, 1):
        valid_ids = {item["source_id"] for item in batch}
        prompt = agent_context.build_prompt(
            task=(
                "提炼本批新闻中最值得注意的事实或共同趋势。严格输出 JSON："
                "{\"claims\":[{\"text\":\"不超过一句\",\"source_ids\":[\"输入ID\"]}]}。"
                "每条结论必须引用至少一个输入 source_id，不得补充输入外事实。"
            ),
            query=f"晨读结论批次 {batch_index}/{len(batches)}。",
            context=json.dumps({"sources": batch}, ensure_ascii=False),
        )
        try:
            result = agent_provider.ask_json("news-takeaway", prompt)
        except Exception as exc:
            print(f"⚠️ Agent 晨读结论批次 {batch_index} 暂不可用: {exc}")
            continue
        for item in (result or {}).get("claims", []):
            if not isinstance(item, dict):
                continue
            refs = {str(value) for value in item.get("source_ids", [])}
            text = str(item.get("text", "")).strip()
            if text and refs and refs <= valid_ids and text not in claims:
                claims.append(text)
    return "；".join(claims[:3]) or "本次未生成可回溯的晨读结论，请以原文链接为准。"
