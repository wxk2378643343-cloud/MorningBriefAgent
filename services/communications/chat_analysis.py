"""Agent analysis for normalized communication records."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from core.agent import context as agent_context
from core.agent import provider as agent_provider
from core.pipeline import AgentBatcher


def _split_record(
    record: Dict[str, Any],
    messages: List[Any],
    *,
    max_chars: int = 12000,
) -> List[Dict[str, Any]]:
    """Split one conversation without dropping messages."""
    base = {key: value for key, value in record.items() if key != "messages"}
    if not messages:
        return [{**base, "messages": []}]
    chunks: List[Dict[str, Any]] = []
    current: List[Any] = []
    for message in messages:
        candidate = current + [message]
        size = len(json.dumps(
            {**base, "messages": candidate},
            ensure_ascii=False,
            default=str,
        ))
        if current and size > max_chars:
            chunks.append({**base, "messages": current})
            current = [message]
        else:
            current = candidate
    if current:
        chunks.append({**base, "messages": current})
    return chunks


def _build_agent_batches(
    private_chats: List[Dict[str, Any]],
    group_chats: List[Dict[str, Any]],
    date_str: str,
    *,
    max_batch_chars: int = 20000,
) -> List[Dict[str, Any]]:
    """Build bounded batches that still cover every selected message."""
    units: List[tuple[str, Dict[str, Any]]] = []
    for index, chat in enumerate(private_chats):
        record = {
            "index": index,
            "name": chat.get("name", ""),
            "time_span": chat.get("time_span", ""),
            "messages": chat.get("messages", []),
        }
        units.extend(
            ("private", part)
            for part in _split_record(record, record["messages"])
        )
    for index, chat in enumerate(group_chats):
        record = {
            "index": index,
            "name": chat.get("name", ""),
            "messages": chat.get("messages")
            or chat.get("my_messages", []) + chat.get("other_messages", []),
        }
        units.extend(
            ("groups", part)
            for part in _split_record(record, record["messages"])
        )

    tagged_units = [{"kind": kind, "record": unit} for kind, unit in units]

    def envelope(values: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "date": date_str,
            "private": [
                item["record"] for item in values if item["kind"] == "private"
            ],
            "groups": [
                item["record"] for item in values if item["kind"] == "groups"
            ],
        }

    return [
        envelope(batch)
        for batch in AgentBatcher[Dict[str, Any]](max_batch_chars).partition(
            tagged_units, envelope=envelope
        )
    ]


def _batch_message_count(batch: Dict[str, Any]) -> int:
    return sum(
        len(record.get("messages", []))
        for kind in ("private", "groups")
        for record in batch.get(kind, [])
    )


def _merge_agent_items(
    target: Dict[int, Dict[str, Any]],
    items: List[Any],
    *,
    topic_key: str,
) -> None:
    for item in items:
        if not isinstance(item, dict) or not str(item.get("index", "")).isdigit():
            continue
        index = int(item["index"])
        merged = target.setdefault(index, {
            topic_key: [],
            "action_items": [],
            "reflections": [],
            "priority": "normal",
        })
        topic_values = item.get(topic_key, [])
        if isinstance(topic_values, str):
            topic_values = [topic_values]
        for value in topic_values:
            text = str(value).strip()
            if text and text not in merged[topic_key]:
                merged[topic_key].append(text)
        for value in item.get("action_items", []):
            text = str(value).strip()
            if text and text not in merged["action_items"]:
                merged["action_items"].append(text)
        reflection = str(item.get("reflection", "")).strip()
        if reflection and reflection not in merged["reflections"]:
            merged["reflections"].append(reflection)
        if item.get("priority") == "high":
            merged["priority"] = "high"


def analyze_and_reflect(
    private_chats: List[Dict[str, Any]],
    group_chats: List[Dict[str, Any]],
    date_str: str,
) -> Dict[str, Any]:
    """Analyze extracted chats with the existing single Agent boundary."""
    print("🧠 [Step 4/5] 将结构化沟通记录交给本地 Agent 分析...")

    batches = _build_agent_batches(private_chats, group_chats, date_str)
    private_analysis: Dict[int, Dict[str, Any]] = {}
    group_analysis: Dict[int, Dict[str, Any]] = {}
    overall_parts: List[str] = []
    successful_batches = 0
    analyzed_message_count = 0
    for batch_index, batch in enumerate(batches, 1):
        print(f"  Agent 分批分析 {batch_index}/{len(batches)}")
        try:
            parsed = agent_provider.ask_json(
                "chat-digest",
                agent_context.build_prompt(
                    task=(
                        "分析提供的私聊和群聊记录。返回严格 JSON，不要输出 Markdown："
                        "{\"private\":[{\"index\":0,\"topics\":[\"事实主题\"],"
                        "\"action_items\":[\"明确承诺或待跟进事项\"],"
                        "\"reflection\":\"基于原文的简短观察\","
                        "\"priority\":\"high|normal|low\"}],"
                        "\"groups\":[{\"index\":0,\"topic\":[\"事实主题\"],"
                        "\"action_items\":[\"明确事项\"],"
                        "\"reflection\":\"基于原文的简短观察\","
                        "\"priority\":\"high|normal|low\"}],"
                        "\"overall\":\"本批次简短摘要\"}。index 必须沿用输入。"
                        "只记录原文明确支持的事实；没有明确承诺时返回空数组，"
                        "不要猜测用户目标、身份、关系、作息或情绪。"
                    ),
                    query=f"{date_str}，批次 {batch_index}/{len(batches)}",
                    context=json.dumps(batch, ensure_ascii=False, default=str),
                ),
            )
            if not isinstance(parsed, dict):
                continue
            successful_batches += 1
            analyzed_message_count += _batch_message_count(batch)
            _merge_agent_items(
                private_analysis, parsed.get("private", []), topic_key="topics"
            )
            _merge_agent_items(
                group_analysis, parsed.get("groups", []), topic_key="topic"
            )
            overall = str(parsed.get("overall", "")).strip()
            if overall and overall not in overall_parts:
                overall_parts.append(overall)
        except Exception as exc:
            print(f"⚠️ Agent 沟通分析批次 {batch_index} 暂不可用: {exc}")

    detailed_privates = []
    compact_privates = []
    for index, friend in enumerate(private_chats):
        agent_item = private_analysis.get(index, {})
        reflections = agent_item.get("reflections", [])
        sample_msgs = friend["messages"]
        meaningful_msgs = [
            message for message in sample_msgs
            if len(message[2]) > 3 and not message[2].startswith("[")
        ] or sample_msgs
        if len(meaningful_msgs) > 5:
            selected = [
                meaningful_msgs[0],
                meaningful_msgs[len(meaningful_msgs) // 2],
                *meaningful_msgs[-3:],
            ]
            seen = set()
            selected_excerpts = []
            for item in selected:
                marker = tuple(item)
                if marker not in seen:
                    seen.add(marker)
                    selected_excerpts.append(item)
        else:
            selected_excerpts = meaningful_msgs

        item_data = {
            "name": friend["name"],
            "total_count": friend["total_count"],
            "my_count": friend["my_count"],
            "friend_count": friend["friend_count"],
            "time_span": friend["time_span"],
            "topics": "、".join(agent_item.get("topics", []))
            or "Agent 未提取到明确主题。",
            "sample_excerpts": selected_excerpts,
            "all_messages": sample_msgs,
            "action_items": agent_item.get("action_items", [])[:3],
            "reflection": "；".join(reflections[:2]) or "Agent 未生成额外反思。",
        }
        (detailed_privates if friend["total_count"] >= 5 else compact_privates).append(
            item_data
        )

    group_summaries = []
    for index, group in enumerate(group_chats):
        agent_item = group_analysis.get(index, {})
        reflections = agent_item.get("reflections", [])
        group_summaries.append({
            "name": group["name"],
            "is_spoke": group["is_spoke"],
            "my_count": group["my_count"],
            "total_count": group["total_count"],
            "all_messages": group.get("messages", []),
            "my_messages": group["my_messages"][:4],
            "topic": "、".join(agent_item.get("topic", []))
            or "Agent 未提取到明确主题。",
            "reflection": "；".join(reflections[:2]) or "Agent 未生成额外反思。",
        })

    return {
        "date_str": date_str,
        "private_count": len(private_chats),
        "detailed_privates": detailed_privates,
        "compact_privates": compact_privates,
        "group_summaries": group_summaries,
        "agent_summary": "\n\n".join(overall_parts) or "Agent 分析暂不可用。",
        "analysis_batches": len(batches),
        "planned_batches": len(batches),
        "successful_batches": successful_batches,
        "failed_batches": len(batches) - successful_batches,
        "source_message_count": sum(
            len(chat.get("messages", [])) for chat in private_chats
        ) + sum(
            len(chat.get("messages") or (
                chat.get("my_messages", []) + chat.get("other_messages", [])
            ))
            for chat in group_chats
        ),
        "analyzed_message_count": analyzed_message_count,
    }
