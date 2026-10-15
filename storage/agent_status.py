"""Read-only summaries for the desktop Agent runtime panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from storage.sqlite import connect, initialize


def read_agent_status(database_path: str | Path | None = None) -> dict[str, Any]:
    database = initialize(database_path)
    with connect(database) as connection:
        latest = connection.execute(
            """
            SELECT task, provider, input_tokens, output_tokens, total_tokens,
                   duration_ms, status, created_at
            FROM agent_usage_records
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        recent = connection.execute(
            """
            SELECT task, provider, input_tokens, output_tokens, total_tokens,
                   duration_ms, status, created_at
            FROM agent_usage_records
            ORDER BY id DESC LIMIT 20
            """
        ).fetchall()
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        sync = {"pending": 0, "failed": 0}
        if "sync_outbox" in tables:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM sync_outbox "
                "WHERE status IN ('pending', 'failed') GROUP BY status"
            ).fetchall()
            sync.update({str(row["status"]): int(row["count"]) for row in rows})
    return {
        "latest": dict(latest) if latest else None,
        "recent": [dict(row) for row in recent],
        "sync": sync,
    }
