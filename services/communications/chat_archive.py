"""Obsidian archive adapter for communication digests."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def archive_to_obsidian(
    analysis: Dict[str, Any],
    archive_dir: str,
) -> Optional[str]:
    """Write a detailed communication report to the configured archive."""
    if not archive_dir:
        return None
    date_range = analysis["date_str"]
    clean_date = date_range.split("~")[0].strip() if "~" in date_range else date_range[:10]
    os.makedirs(archive_dir, exist_ok=True)
    file_path = os.path.join(
        archive_dir, f"{clean_date}-全量私聊与精选群聊复盘.md"
    )
    detailed = analysis["detailed_privates"]
    compact = analysis["compact_privates"]
    lines = [
        "---",
        f"title: \"{clean_date}-全量私聊与精选群聊复盘\"",
        f"date: {clean_date}",
        "project: \"聊天习惯与社交数据\"",
        "status: \"已归档\"",
        "tags: [\"微信\", \"私聊复盘\", \"全量好友\", \"精选群聊\", \"沟通自省\", \"AGY\"]",
        "---",
        "",
        f"# 🌅 每日私聊全员与精选群聊深度复盘 ({date_range})",
        "",
        "## 一、社交全景概况",
        f"- **1v1 私聊全员覆盖**：{len(detailed) + len(compact)} 位联系人 "
        f"(深度高频 {len(detailed)} 位 | 轻量联络 {len(compact)} 位)",
        f"- **精选重点群聊数**：{len(analysis['group_summaries'])} 个",
        "",
        "## 二、重点好友深度复盘 (高频交流 ≥ 5条)",
        "",
    ]
    for person in detailed:
        lines.extend([
            f"### 【{person['name']}】 (总计 {person['total_count']} 条 | "
            f"本人 {person['my_count']} 条 | 时段 {person['time_span']})",
            f"- **核心议题**：{person['topics']}",
            *(
                [f"- **承诺/待跟进**：{'、'.join(person['action_items'])}"]
                if person["action_items"] else []
            ),
            f"- **沟通反思**：{person['reflection']}",
            "",
        ])
        if person.get("all_messages"):
            lines.append("#### 💬 全量对话时间流流水")
            lines.extend(
                f"- {message[3] if len(message) > 3 else '💬'} "
                f"`[{message[0]}]` **{message[1]}**：{message[2]}"
                for message in person["all_messages"]
            )
            lines.append("")
    if compact:
        lines.extend(["## 三、日常轻量联络清单 (全量留痕 < 5条)", ""])
        lines.extend(
            f"- **【{person['name']}】** (`{person['time_span']}` | "
            f"来往 {person['total_count']} 条)：{person['topics']}"
            for person in compact
        )
        lines.append("")
    lines.extend(["## 四、精选重点群聊动态", ""])
    for group in analysis["group_summaries"]:
        lines.extend([
            f"### 【{group['name']}】 "
            f"({'本人实际发言' if group['is_spoke'] else '静默关注'})",
            f"- **议题脉络**：{group['topic']}",
        ])
        if group["my_messages"]:
            lines.append("- **本人发言记录**：")
            lines.extend(
                f"  - {message[3] if len(message) > 3 else '💬'} "
                f"`[{message[0]}]` {message[2]}"
                for message in group["my_messages"]
            )
        lines.extend([f"- **复盘反思**：{group['reflection']}", ""])
    lines.extend([
        "## 五、综合认知自省与行动闭环",
        "1. **主题聚焦**：由 Agent 根据消息内容识别值得关注的主题与风险。",
        "2. **边界管理**：由本地知识库中已配置的偏好决定提醒与行动边界。",
        "3. **行动闭环**：对消息中明确提到的承诺建立可追踪事项，避免凭空推断。",
        "",
    ])
    with open(file_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
    print(f"📁 [Step 5/5] 复盘报告已归档至 Obsidian: {file_path}")
    return file_path
