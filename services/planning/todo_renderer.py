"""Pure rendering for planning cards."""

from __future__ import annotations

from typing import Any


def build_evening_review_card(plan: dict[str, Any]) -> dict[str, Any]:
    todos = plan.get("todos", [])
    slots = plan.get("schedule_slots", [])
    analysis = plan.get("analysis", {})
    todo_lines = [
        f"• [ ] **{item}** *(Agent 提炼)*" for item in todos
    ] or ["• 暂无通过事实校验的明确待办"]
    slot_lines = [
        f"• **{item['name']}**：`{item['start']} ~ {item['end']}` "
        f"({str(item.get('summary', '')).split('：')[-1]})"
        for item in slots
    ] or ["• 暂无具有明确时间约束的日程"]
    prompt_body = (
        f"晚上好！🌙 正在为你预排 **{plan['date']} ({plan['weekday']})** "
        "的待办与日程：\n\n"
        "📋 **【明日核心待办预排】**\n"
        + "\n".join(todo_lines)
        + "\n\n⏱️ **【明日作息日程预排】**\n"
        + "\n".join(slot_lines)
        + (
            f"\n\n🔎 已分析 {len(plan.get('candidates', []))} 条候选，"
            f"采纳 {len(todos)} 项，"
            f"排除 {len(analysis.get('rejected_items', []))} 项。"
        )
        + "\n\n❓ **以上待办与时间盒排期是否合适？**\n\n"
        "💬 *如需调整时间或事项，可直接在飞书回复：*\n"
        "• “**把某个时间块改到 18:00**”\n"
        "• “**加上：明天要处理一件事**”\n"
        "• “**确认排期**” ➔ 锁定排期并写入飞书日历与任务列表"
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"🌙 明日待办与日程综合预审 ({plan['date']})",
            },
            "template": "indigo",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": prompt_body}},
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [{
                    "tag": "plain_text",
                    "content": "🤖 Agent 统合预审 | 确认后写入本地归档、任务与日历",
                }],
            },
        ],
    }
