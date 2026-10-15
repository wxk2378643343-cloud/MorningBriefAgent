"""Semantic extraction boundary between raw chat candidates and planning."""

from __future__ import annotations

import json
from typing import Any, Iterable

from core.agent import context as agent_context
from core.agent import provider as agent_provider
from core.pipeline import AgentBatcher


def analyze_candidates(
    candidates: Iterable[str],
    target_date: str,
) -> dict[str, Any]:
    """Use one structured Agent pass to accept/reject candidate commitments."""
    raw = [str(item).strip() for item in candidates if str(item).strip()]
    if not raw:
        return {
            "target_date": target_date,
            "valid_items": [],
            "rejected_items": [],
            "constraints": [],
        }

    valid_items: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    constraints: list[str] = []
    seen: set[str] = set()
    batches = AgentBatcher[str](16000).partition(
        raw, envelope=lambda values: {"candidates": values}
    )
    successful_batches = 0
    for batch_index, batch in enumerate(batches, 1):
        prompt = agent_context.build_prompt(
            task=(
                "你是待办事实分析器。逐条判断输入是否是用户本人需要执行、跟进或确认"
                "的明确事项。广告、新闻、闲聊、他人广播、纯提问、已经完成的事项必须"
                "拒绝。不要发明截止时间或任务。严格输出 JSON："
                "{\"valid_items\":[{\"title\":\"可执行标题\",\"source_text\":\"原句\","
                "\"confidence\":0.0,\"reason\":\"依据\"}],"
                "\"rejected_items\":[{\"source_text\":\"原句\",\"reason\":\"原因\"}],"
                "\"constraints\":[\"资料明确出现的日期或时间约束\"]}。"
            ),
            query=(
                f"目标计划日期：{target_date}；"
                f"批次 {batch_index}/{len(batches)}"
            ),
            context=json.dumps({"candidates": batch}, ensure_ascii=False),
        )
        try:
            result = agent_provider.ask_json("todo-fact-analysis", prompt)
        except Exception as exc:
            print(f"⚠️ 待办事实分析批次 {batch_index} 暂不可用: {exc}")
            result = None
        if not isinstance(result, dict):
            rejected.extend(
                {"source_text": item, "reason": "Agent 分析未完成"} for item in batch
            )
            continue
        successful_batches += 1
        for item in result.get("valid_items", []):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            source_text = str(item.get("source_text", "")).strip()
            try:
                confidence = float(item.get("confidence", 0))
            except (TypeError, ValueError):
                confidence = 0
            if title and source_text in batch and confidence >= 0.6 and title not in seen:
                seen.add(title)
                valid_items.append({
                    "title": title,
                    "source_text": source_text,
                    "confidence": min(confidence, 1.0),
                    "reason": str(item.get("reason", "")).strip(),
                })
        rejected.extend(
            item for item in result.get("rejected_items", [])
            if isinstance(item, dict)
            and str(item.get("source_text", "")).strip() in batch
        )
        constraints.extend(
            str(value).strip() for value in result.get("constraints", [])
            if str(value).strip()
        )
    return {
        "target_date": target_date,
        "valid_items": valid_items,
        "rejected_items": rejected,
        "constraints": list(dict.fromkeys(constraints)),
        "planned_batches": len(batches),
        "successful_batches": successful_batches,
        "failed_batches": len(batches) - successful_batches,
    }
