"""Agent analysis for normalized communication records."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from core.agent import context as agent_context
from core.agent import provider as agent_provider


def analyze_and_reflect(
    private_chats: List[Dict[str, Any]],
    group_chats: List[Dict[str, Any]],
    date_str: str,
) -> Dict[str, Any]:
    """Analyze extracted chats with the existing single Agent boundary."""
    print("🧠 [Step 4/5] 将结构化沟通记录交给本地 Agent 分析...")

    raw_context = json.dumps(
        {"date": date_str, "private": private_chats, "groups": group_chats},
        ensure_ascii=False,
        default=str,
    )[:24000]
    agent_result: Dict[str, Any] = {}
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
                    "\"groups\":[{\"index\":0,\"topic\":\"事实主题\","
                    "\"action_items\":[\"明确事项\"],"
                    "\"reflection\":\"基于原文的简短观察\","
                    "\"priority\":\"high|normal|low\"}],"
                    "\"overall\":\"不超过三段的整体摘要\"}。"
                    "只记录原文明确支持的事实；没有明确承诺时返回空数组，"
                    "不要猜测用户目标、身份、关系、作息或情绪。"
                ),
                query=date_str,
                context=raw_context,
            ),
        )
        if isinstance(parsed, dict):
            agent_result = parsed
    except Exception as exc:
        print(f"⚠️ Agent 沟通分析暂不可用: {exc}")

    private_analysis = {
        int(item["index"]): item
        for item in agent_result.get("private", [])
        if isinstance(item, dict) and str(item.get("index", "")).isdigit()
    }
    group_analysis = {
        int(item["index"]): item
        for item in agent_result.get("groups", [])
        if isinstance(item, dict) and str(item.get("index", "")).isdigit()
    }

    detailed_privates = []
    compact_privates = []
    for index, friend in enumerate(private_chats):
        agent_item = private_analysis.get(index, {})
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
            "reflection": agent_item.get("reflection", "Agent 未生成额外反思。"),
        }
        (detailed_privates if friend["total_count"] >= 5 else compact_privates).append(
            item_data
        )

    group_summaries = []
    for index, group in enumerate(group_chats):
        agent_item = group_analysis.get(index, {})
        group_summaries.append({
            "name": group["name"],
            "is_spoke": group["is_spoke"],
            "my_count": group["my_count"],
            "total_count": group["total_count"],
            "my_messages": group["my_messages"][:4],
            "topic": agent_item.get("topic", "Agent 未提取到明确主题。"),
            "reflection": agent_item.get("reflection", "Agent 未生成额外反思。"),
        })

    return {
        "date_str": date_str,
        "private_count": len(private_chats),
        "detailed_privates": detailed_privates,
        "compact_privates": compact_privates,
        "group_summaries": group_summaries,
        "agent_summary": agent_result.get("overall", "Agent 分析暂不可用。"),
    }
