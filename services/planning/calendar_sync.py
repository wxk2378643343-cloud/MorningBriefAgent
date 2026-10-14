"""Application service for synchronizing plan calendar slots."""

from __future__ import annotations

import datetime
from typing import Any

from core.agent.contracts import AgentPlan
from core.integrations.feishu import idempotency
from core.integrations.sync_outbox import sync_outbox


def sync_plan_to_calendar(plan_data: dict[str, Any], gateway) -> int:
    plan = AgentPlan.from_dict(plan_data)
    written_count = 0
    target_date = datetime.date.fromisoformat(plan.date)
    for slot in plan.schedule_slots:
        key = idempotency.make_key(
            "feishu-calendar", plan.date, slot.name, slot.start, slot.end, slot.summary
        )
        sync_outbox.begin(
            key,
            "feishu.calendar",
            {
                "date": plan.date,
                "slot_key": key,
                "name": slot.name,
                "start": slot.start,
                "end": slot.end,
                "summary": slot.summary,
                "description": slot.desc or slot.summary,
            },
        )
        try:
            start = datetime.datetime.combine(
                target_date, datetime.time.fromisoformat(slot.start)
            )
            end = datetime.datetime.combine(
                target_date, datetime.time.fromisoformat(slot.end)
            )
            result, _ = idempotency.store.execute_once(
                key,
                lambda: gateway.create_calendar_event(
                    summary=slot.summary,
                    start_dt=start,
                    end_dt=end,
                    description=slot.desc or slot.summary,
                    reminder_minutes=15,
                ),
                success=lambda value: bool(value and value[0]),
            )
            sync_outbox.finish(key, bool(result and result[0]))
            if result and result[0]:
                written_count += 1
        except Exception as exc:
            sync_outbox.finish(key, False, str(exc))
            continue
    return written_count
