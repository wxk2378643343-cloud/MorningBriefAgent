from __future__ import annotations

TODO_VALID_STATUSES = {"open", "completed", "cancelled", "postponed"}

def _record_audit(
    connection,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    before_value: str | None = None,
    after_value: str | None = None,
    actor: str = "desktop_user",
) -> None:
    connection.execute(
        """
        INSERT INTO audit_log
          (entity_type, entity_id, action, before_value, after_value, actor, created_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (entity_type, entity_id, action, before_value, after_value, actor),
    )
"""Repositories for synchronized todo and calendar facts."""


import hashlib
from typing import Any
from datetime import datetime, timezone

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
        existing = connection.execute(
            "SELECT status, priority, due_date, feishu_task_id FROM todo_records WHERE id = ?",
            (todo_id,),
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO todo_records
                  (id, source_id, title, status, priority, due_date, feishu_task_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (todo_id, source_id, title, status, priority, due_date, feishu_task_id),
            )
            _record_audit(
                connection,
                entity_type="todo",
                entity_id=todo_id,
                action="create",
                after_value=title,
            )
        else:
            changed = (
                existing["status"] != status
                or existing["priority"] != priority
                or existing["due_date"] != due_date
                or existing["feishu_task_id"] != feishu_task_id
            )
            if changed:
                connection.execute(
                    """
                    UPDATE todo_records
                    SET status=?, priority=?, due_date=?, feishu_task_id=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (status, priority, due_date, feishu_task_id, todo_id),
                )
                _record_audit(
                    connection,
                    entity_type="todo",
                    entity_id=todo_id,
                    action="update",
                    before_value=f"status={existing['status']}, priority={existing['priority']}",
                    after_value=f"status={status}, priority={priority}",
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
        existing = connection.execute(
            "SELECT feishu_event_id, sync_status FROM schedule_records WHERE id = ?",
            (event_id,),
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO schedule_records
                  (id, source_id, title, start_at, end_at, feishu_event_id, sync_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, source_id, title, start_at, end_at,
                    feishu_event_id, sync_status,
                ),
            )
            _record_audit(
                connection,
                entity_type="schedule",
                entity_id=event_id,
                action="create",
                after_value=f"{title} ({start_at} - {end_at})",
            )
        else:
            changed = (
                existing["feishu_event_id"] != feishu_event_id
                or existing["sync_status"] != sync_status
            )
            if changed:
                connection.execute(
                    """
                    UPDATE schedule_records
                    SET feishu_event_id=?, sync_status=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (feishu_event_id, sync_status, event_id),
                )
                _record_audit(
                    connection,
                    entity_type="schedule",
                    entity_id=event_id,
                    action="update",
                    before_value=f"sync_status={existing['sync_status']}",
                    after_value=f"sync_status={sync_status}",
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
    *, status: str | None = None, due_date: str | None = None, database_path: str | None = None
) -> list[dict[str, Any]]:
    initialize(database_path)
    query = "SELECT * FROM todo_records"
    params: list[Any] = []
    clauses: list[str] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if due_date:
        clauses.append("due_date = ?")
        params.append(due_date)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY due_date IS NULL, due_date, priority, created_at DESC"
    with connect(database_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def update_todo_status(
    todo_id: str,
    status: str,
    *,
    database_path: str | None = None,
) -> bool:
    if status not in TODO_VALID_STATUSES:
        raise ValueError(f"invalid_todo_status:{status}")
    initialize(database_path)
    with connect(database_path) as connection:
        current_row = connection.execute(
            "SELECT status, title FROM todo_records WHERE id = ?", (todo_id,)
        ).fetchone()
        if not current_row:
            return False
        old_status = current_row["status"]
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
        if cursor.rowcount > 0:
            _record_audit(
                connection,
                entity_type="todo",
                entity_id=todo_id,
                action=f"status_change_to_{status}",
                before_value=old_status,
                after_value=status,
            )
            return True
        return False


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
        conditions.append("start_at < ?")
        params.append(end_date)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY start_at ASC"
    with connect(database_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]



def parse_audit_time(val: str | None) -> str | None:
    """Parse and normalize time string to SQLite UTC format 'YYYY-MM-DD HH:MM:SS'.

    Strict requirements:
    1. If val is empty, return None.
    2. Must contain explicit timezone indicator: 'Z' or offset like '+08:00', '-05:00'.
    3. If val has no timezone indicator, raise ValueError('invalid_time_range').
    4. Internal storage format: if val is already normalized 'YYYY-MM-DD HH:MM:SS' and internal,
       we only allow ISO strings with explicit timezones for public inputs.
    """
    if not val:
        return None
    val = val.strip()
    # Check for timezone indicator
    has_tz = val.endswith("Z") or ("T" in val and ("+" in val[10:] or "-" in val[10:]))
    if not has_tz:
        raise ValueError("invalid_time_range")
    try:
        # Standardize 'Z' to '+00:00' for fromisoformat
        iso_str = val[:-1] + "+00:00" if val.endswith("Z") else val
        dt = datetime.fromisoformat(iso_str)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        raise ValueError("invalid_time_range") from exc


def list_audit_logs(
    *,
    entity_type: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 50,
    database_path: str | None = None,
) -> list[dict[str, Any]]:
    initialize(database_path)
    parsed_start = parse_audit_time(start_time)
    parsed_end = parse_audit_time(end_time)

    query = "SELECT * FROM audit_log"
    params: list[Any] = []
    conditions = []
    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if parsed_start:
        conditions.append("created_at >= ?")
        params.append(parsed_start)
    if parsed_end:
        conditions.append("created_at < ?")
        params.append(parsed_end)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with connect(database_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]
