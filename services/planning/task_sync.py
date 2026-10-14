"""Application service for synchronizing plan tasks."""

from __future__ import annotations

from typing import Any, Callable

from core.agent.contracts import AgentPlan
from core.integrations.feishu import idempotency


def sync_plan_to_feishu_tasks(
    plan_data: dict[str, Any],
    create_task: Callable[..., dict | None],
) -> int:
    plan = AgentPlan.from_dict(plan_data)
    created_count = 0
    for title in plan.todos:
        key = idempotency.make_key("feishu-task", plan.date, title)
        try:
            task = create_task(
                summary=title,
                description=f"{plan.date} 核心作战待办（已同步 Obsidian 知识库）",
                idempotency_key=key,
            )
            if task:
                created_count += 1
        except Exception:
            # The create service records the failed outbox attempt; continue
            # syncing independent tasks so one provider error is isolated.
            continue
    return created_count
