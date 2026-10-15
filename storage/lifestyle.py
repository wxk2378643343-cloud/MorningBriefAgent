"""Repositories for confirmed and pending lifestyle measurements."""

from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any

from .sqlite import connect, initialize, insert_audit


def save_meal_estimate(
    fact_id: str,
    *,
    calories: float | None = None,
    protein: float | None = None,
    database_path: str | None = None,
) -> None:
    """Save an estimate as pending; it is excluded from confirmed totals."""
    initialize(database_path)
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO meal_records
              (fact_id, calories_estimated, protein_estimated)
            VALUES (?, ?, ?)
            ON CONFLICT(fact_id) DO UPDATE SET
              calories_estimated=excluded.calories_estimated,
              protein_estimated=excluded.protein_estimated,
              updated_at=CURRENT_TIMESTAMP
            """.replace(",\n              updated_at=CURRENT_TIMESTAMP", ""),
            (fact_id, calories, protein),
        )


def confirm_meal(
    fact_id: str,
    *,
    calories: float,
    actor: str,
    database_path: str | None = None,
) -> bool:
    """Promote a user-confirmed value and retain the audit trail."""
    initialize(database_path)
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT calories_confirmed FROM meal_records WHERE fact_id = ?",
            (fact_id,),
        ).fetchone()
        if row is None:
            return False
        before = dict(row)
        connection.execute(
            """
            UPDATE meal_records
            SET calories_confirmed=?, confirmation_status='confirmed',
                confirmed_by=?, confirmed_at=?
            WHERE fact_id=?
            """,
            (calories, actor, dt.datetime.now().isoformat(timespec="seconds"), fact_id),
        )
        insert_audit(
            connection,
            entity_type="meal_record",
            entity_id=fact_id,
            action="confirm",
            actor=actor,
            before_value=before,
            after_value={"calories_confirmed": calories},
        )
    return True


def get_meal(fact_id: str, *, database_path: str | None = None) -> dict[str, Any] | None:
    initialize(database_path)
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT f.*, m.calories_estimated, m.calories_confirmed,
                   m.protein_estimated, m.confirmation_status
            FROM fact_records f
            LEFT JOIN meal_records m ON m.fact_id = f.id
            WHERE f.id=?
            """,
            (fact_id,),
        ).fetchone()
    return dict(row) if row else None
