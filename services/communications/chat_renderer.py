"""Presentation adapter for communication digest cards."""

from __future__ import annotations

from typing import Any, Dict


def build_feishu_card(
    analysis: Dict[str, Any],
    total_all_groups: int,
) -> Dict[str, Any]:
    date_str = analysis["date_str"]
    detailed = analysis["detailed_privates"]
    compact = analysis["compact_privates"]
    groups = analysis["group_summaries"]
    total_messages = sum(item["total_count"] for item in detailed + compact)
    ignored_groups = total_all_groups - len(groups)
    planned = analysis.get("planned_batches", analysis.get("analysis_batches", 1))
    successful = analysis.get("successful_batches", planned)
    failed = analysis.get("failed_batches", max(0, planned - successful))
    analyzed = analysis.get("analyzed_message_count")
    source_count = analysis.get("source_message_count")
    if failed:
        agent_coverage = (
            f"⚠️ **Agent 覆盖不完整**：成功 {successful}/{planned} 批"
            + (
                f"，已分析 {analyzed}/{source_count} 条入选消息"
                if analyzed is not None and source_count is not None else ""
            )
        )
    else:
        agent_coverage = (
            f"✅ **Agent 覆盖**：成功处理 {successful}/{planned} 批"
            + (
                f"，共 {analyzed} 条入选消息"
                if analyzed is not None else ""
            )
        )
    elements = [{
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": (
                f"**📊 社交与沟通全景概览 ({date_str})**\n"
                f"• **私聊全员覆盖**：共与 **{len(detailed) + len(compact)} 位联系人** "
                f"产生交流 (累计 {total_messages} 条消息，完整计数、重点摘录)\n"
                f"• **精选重点群聊**：仅整理 **{len(groups)} 个精选群** "
                f"(本人发言群 {sum(1 for item in groups if item['is_spoke'])} 个)\n"
                f"• **信息防噪专注度**：过滤 **{ignored_groups} 个非目标群聊；"
                f"完整入选记录写入本地归档\n"
                f"• {agent_coverage}"
            ),
        },
    }, {"tag": "hr"}]

    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"### 👤 重点好友深度复盘 (高频交流 ≥ 5条，共 {len(detailed)} 人)",
        },
    })
    for index, person in enumerate(detailed, 1):
        lines = [
            f"**{index}. 【{person['name']}】** "
            f"(来往 {person['total_count']} 条 | 我发 {person['my_count']} 条 | "
            f"时段 {person['time_span']})",
            f"• **交流主题**：{person['topics']}",
        ]
        if person.get("sample_excerpts"):
            lines.append("• **代表性对话流**：")
            for message in person["sample_excerpts"][:3]:
                icon = message[3] if len(message) > 3 else "💬"
                lines.append(
                    f"  - {icon} `[{message[0]}]` **{message[1]}**：{message[2][:75]}"
                )
        if person.get("action_items"):
            lines.append(f"• **承诺/待跟进**：{'、'.join(person['action_items'])}")
        lines.append(f"• **沟通反思**：{person['reflection']}")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})

    elements.append({"tag": "hr"})
    if compact:
        lines = [f"**【💬 日常轻量联络清单】**（< 5条，共 {len(compact)} 人）", ""]
        lines.extend(
            f"• **【{person['name']}】** ({person['time_span']} | 来往 "
            f"{person['total_count']} 条)：{person['topics']}"
            for person in compact
        )
        elements.extend([
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}},
            {"tag": "hr"},
        ])

    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": "**【👥 精选重点群聊动态与发言】**"},
    })
    for group in groups:
        lines = [
            f"**【{group['name']}】** "
            f"({'🟢 本人有发言' if group['is_spoke'] else '👀 静默关注'} | "
            f"我发言 {group['my_count']} 条 / 全群 {group['total_count']} 条)",
            f"• **议题脉络**：{group['topic']}",
        ]
        if group["my_messages"]:
            lines.append("• **发言详录**：")
            for message in group["my_messages"][:3]:
                icon = message[3] if len(message) > 3 else "💬"
                lines.append(f"  - {icon} `[{message[0]}]` {message[2][:75]}")
        lines.append(f"• **群聊自省**：{group['reflection']}")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})

    elements.extend([
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": analysis.get(
                    "agent_summary",
                    "### 🧠 Agent 综合分析\n当前没有可用的额外分析结果，请结合原始消息自行确认重点。",
                ),
            },
        },
    ])
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🌅 每日私聊全员与精选群聊深度复盘 ({date_str})",
                },
                "template": "carmine",
            },
            "elements": elements,
        },
    }
