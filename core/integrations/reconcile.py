"""Replay failed cross-system side effects from the durable sync outbox."""

from __future__ import annotations

import datetime as dt
from typing import Any

from .feishu import idempotency
from .feishu.gateway import feishu_gateway
from .sync_outbox import SyncOutbox, sync_outbox


def _calendar_operation(gateway, payload: dict[str, Any]):
    target_date = dt.date.fromisoformat(payload["date"])
    start = dt.datetime.combine(target_date, dt.time.fromisoformat(payload["start"]))
    end = dt.datetime.combine(target_date, dt.time.fromisoformat(payload["end"]))
    return gateway.create_calendar_event(
        summary=payload["summary"],
        start_dt=start,
        end_dt=end,
        description=payload.get("description", payload["summary"]),
        reminder_minutes=15,
    )


def reconcile_pending(
    limit: int = 100,
    *,
    outbox: SyncOutbox | None = None,
    gateway=None,
    idempotency_store=None,
) -> dict[str, int]:
    """Retry pending/failed Feishu writes using their original payload."""
    journal = outbox or sync_outbox
    provider = gateway or feishu_gateway
    store = idempotency_store or idempotency.store
    records = journal.pending(limit)
    summary = {"examined": len(records), "recovered": 0, "failed": 0}

    for record in records:
        key = record["key"]
        payload = record.get("payload") or {}
        try:
            kind = record["kind"]
            if kind == "feishu.card":
                result, _ = store.execute_once(
                    key,
                    lambda: provider.client.send_card(payload["card"]),
                    success=lambda value: value is True,
                )
            elif kind == "feishu.task":
                # Reuse the application service so its compatibility query
                # can detect tasks created before a response was lost.
                from services.planning.daily_todo import create_feishu_task

                result = create_feishu_task(
                    summary=payload["summary"],
                    description=payload.get("description", ""),
                    due_timestamp=payload.get("due_timestamp"),
                    idempotency_key=key,
                )
            elif kind == "feishu.calendar":
                result, _ = store.execute_once(
                    key,
                    lambda: _calendar_operation(provider, payload),
                    success=lambda value: bool(value and value[0]),
                )
            else:
                raise ValueError(f"unsupported outbox kind: {kind}")

            success = bool(result if kind != "feishu.calendar" else result and result[0])
            journal.finish(key, success, "" if success else "provider returned failure")
            summary["recovered" if success else "failed"] += 1
        except (KeyError, TypeError, ValueError) as exc:
            journal.finish(key, False, f"invalid replay payload: {exc}")
            summary["failed"] += 1
        except Exception as exc:
            journal.finish(key, False, str(exc))
            summary["failed"] += 1

    summary["remaining"] = len(journal.pending())
    return summary
