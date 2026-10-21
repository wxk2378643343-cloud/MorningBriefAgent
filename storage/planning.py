"""Repositories for synchronized todo and calendar facts."""

from __future__ import annotations

import hashlib
from typing import Any

from .sqlite import connect, initialize


def _id(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode()).hexdigest()[:24]}"


def _ensure_source(connection, source_id: str) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO source_records
          (id, source_type, recorded_at)
        VALUES (?, 'structured_input', CURRENT_TIMESTAMP)
        """,
        (source_id,),
    )


def save_todo(
    *,
    title: str,
    source_id: str,
    due_date: str | None = None,
    priority: str = "normal",
    status: str = "open",
    feishu_task_id: str | None = None,
    database_path: str | None = None,
) -> str:
    initialize(database_path)
    todo_id = _id("todo", f"{source_id}:{title}:{due_date or ''}")
    with connect(database_path) as connection:
        _ensure_source(connection, source_id)
        connection.execute(
            """
            INSERT INTO todo_records
              (id, source_id, title, status, priority, due_date, feishu_task_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              status=excluded.status, priority=excluded.priority,
              due_date=excluded.due_date, feishu_task_id=excluded.feishu_task_id,
              updated_at=CURRENT_TIMESTAMP
            """,
            (todo_id, source_id, title, status, priority, due_date, feishu_task_id),
        )
    return todo_id


def save_schedule(
    *,
    title: str,
    source_id: str,
    start_at: str,
    end_at: str,
    feishu_event_id: str | None = None,
    sync_status: str = "pending",
    database_path: str | None = None,
) -> str:
    initialize(database_path)
    event_id = _id("schedule", f"{source_id}:{title}:{start_at}:{end_at}")
    with connect(database_path) as connection:
        _ensure_source(connection, source_id)
        connection.execute(
            """
            INSERT INTO schedule_records
              (id, source_id, title, start_at, end_at, feishu_event_id, sync_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              feishu_event_id=excluded.feishu_event_id,
              sync_status=excluded.sync_status,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                event_id, source_id, title, start_at, end_at,
                feishu_event_id, sync_status,
            ),
        )
    return event_id


def attach_feishu_task_id(
    *,
    title: str,
    source_id: str,
    due_date: str | None,
    feishu_task_id: str,
    database_path: str | None = None,
) -> None:
    initialize(database_path)
    todo_id = _id("todo", f"{source_id}:{title}:{due_date or ''}")
    with connect(database_path) as connection:
        connection.execute(
            "UPDATE todo_records SET feishu_task_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (feishu_task_id, todo_id),
        )


def attach_feishu_event_id(
    *,
    title: str,
    source_id: str,
    start_at: str,
    end_at: str,
    feishu_event_id: str,
    database_path: str | None = None,
) -> None:
    initialize(database_path)
    event_id = _id("schedule", f"{source_id}:{title}:{start_at}:{end_at}")
    with connect(database_path) as connection:
        connection.execute(
            """
            UPDATE schedule_records
            SET feishu_event_id=?, sync_status='synced', updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (feishu_event_id, event_id),
        )


def list_open_todos(
    *, due_date: str | None = None, database_path: str | None = None
) -> list[dict[str, Any]]:
    initialize(database_path)
    query = "SELECT * FROM todo_records WHERE status != 'completed'"
    params: list[Any] = []
    if due_date:
        query += " AND due_date = ?"
        params.append(due_date)
    query += " ORDER BY due_date IS NULL, due_date, priority, created_at"
    with connect(database_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def persist_plan(
    plan: dict[str, Any],
    *,
    database_path: str | None = None,
) -> None:
    """Project a staged plan into queryable todo and schedule records."""
    target_date = str(plan.get("date", "")).strip() or None
    source_id = f"plan:{target_date or 'unknown'}"
    for title in plan.get("todos", []):
        title = str(title).strip()
        if title:
            save_todo(
                title=title,
                source_id=source_id,
                due_date=target_date,
                database_path=database_path,
            )
    for slot in plan.get("schedule_slots", []):
        if not isinstance(slot, dict):
            continue
        name = str(slot.get("name", "")).strip()
        start = str(slot.get("start", "")).strip()
        end = str(slot.get("end", "")).strip()
        if name and start and end and target_date:
            save_schedule(
                title=name,
                source_id=source_id,
                start_at=f"{target_date}T{start}:00",
                end_at=f"{target_date}T{end}:00",
                sync_status="planned",
                database_path=database_path,
            )


def list_all_todos(
    *, status: str | None = None, database_path: str | None = None
) -> list[dict[str, Any]]:
    initialize(database_path)
    query = "SELECT * FROM todo_records"
    params: list[Any] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY due_date IS NULL, due_date, priority, created_at DESC"
    with connect(database_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def update_todo_status(
    todo_id: str,
    status: str,
    *,
    database_path: str | None = None,
) -> bool:
    initialize(database_path)
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE todo_records
            SET status=?,
                completed_at=CASE WHEN ? = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (status, status, todo_id),
        )
        return cursor.rowcount > 0


def list_schedules(
    *, start_date: str | None = None, end_date: str | None = None, database_path: str | None = None
) -> list[dict[str, Any]]:
    initialize(database_path)
    query = "SELECT * FROM schedule_records"
    params: list[Any] = []
    conditions = []
    if start_date:
        conditions.append("start_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("start_at <= ?")
        params.append(end_date)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY start_at ASC"
    with connect(database_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]
