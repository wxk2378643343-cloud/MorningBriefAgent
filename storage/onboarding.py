"""Small local state machine for the first-run desktop onboarding flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from storage.sqlite import connect, initialize


ONBOARDING_STEPS = (
    "workspace",
    "provider",
    "channel",
    "profile",
)


def get_status(database_path: str | Path | None = None) -> dict[str, Any]:
    initialize(database_path)
    with connect(database_path) as connection:
        rows = connection.execute(
            "SELECT step_key, status, detail, completed_at "
            "FROM onboarding_steps ORDER BY rowid"
        ).fetchall()
    by_key = {str(row["step_key"]): dict(row) for row in rows}
    steps = [
        by_key.get(
            key,
            {"step_key": key, "status": "pending", "detail": None, "completed_at": None},
        )
        for key in ONBOARDING_STEPS
    ]
    completed = sum(item["status"] == "completed" for item in steps)
    current = next(
        (item["step_key"] for item in steps if item["status"] != "completed"),
        None,
    )
    return {
        "steps": steps,
        "completed_count": completed,
        "total_count": len(steps),
        "complete": completed == len(steps),
        "current_step": current,
    }


def complete_step(
    step_key: str,
    *,
    detail: str | None = None,
    database_path: str | Path | None = None,
) -> None:
    if step_key not in ONBOARDING_STEPS:
        raise ValueError(f"Unknown onboarding step: {step_key}")
    initialize(database_path)
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO onboarding_steps
              (step_key, status, detail, completed_at)
            VALUES (?, 'completed', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(step_key) DO UPDATE SET
              status='completed',
              detail=excluded.detail,
              completed_at=CURRENT_TIMESTAMP,
              updated_at=CURRENT_TIMESTAMP
            """,
            (step_key, detail),
        )


def reset_step(
    step_key: str,
    *,
    database_path: str | Path | None = None,
) -> None:
    if step_key not in ONBOARDING_STEPS:
        raise ValueError(f"Unknown onboarding step: {step_key}")
    initialize(database_path)
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO onboarding_steps (step_key, status)
            VALUES (?, 'pending')
            ON CONFLICT(step_key) DO UPDATE SET
              status='pending',
              detail=NULL,
              completed_at=NULL,
              updated_at=CURRENT_TIMESTAMP
            """,
            (step_key,),
        )
