"""Bounded, persistent parent/subtask lifecycle orchestration."""

from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from storage.sqlite import connect, initialize


TERMINAL_STATES = {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class SubtaskLimits:
    max_concurrency: int = 4
    max_depth: int = 2
    max_tasks: int = 32
    max_retries: int = 2


class SubtaskError(ValueError):
    pass


def create_subtask(
    parent_id: str,
    task_type: str,
    payload: dict[str, Any],
    *,
    depth: int = 1,
    idempotency_key: str,
    timeout_seconds: int = 60,
    database_path: str | os.PathLike[str] | None = None,
    limits: SubtaskLimits = SubtaskLimits(),
) -> dict[str, Any]:
    initialize(database_path)
    if not parent_id.strip() or not task_type.strip() or not idempotency_key.strip():
        raise SubtaskError("parent_type_and_idempotency_required")
    if not 1 <= depth <= limits.max_depth:
        raise SubtaskError("subtask_depth_exceeded")
    if not 1 <= timeout_seconds <= 3600:
        raise SubtaskError("invalid_subtask_timeout")
    with connect(database_path) as database:
        count = database.execute(
            "SELECT COUNT(*) FROM agent_subtasks WHERE parent_id = ?",
            (parent_id,),
        ).fetchone()[0]
        if count >= limits.max_tasks:
            raise SubtaskError("subtask_limit_exceeded")
        existing = database.execute(
            "SELECT * FROM agent_subtasks WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return _decode(dict(existing))
        task_id = f"subtask-{uuid.uuid4().hex}"
        database.execute(
            """
            INSERT INTO agent_subtasks
              (id, parent_id, task_type, depth, status, payload,
               idempotency_key, timeout_seconds, max_retries)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                task_id,
                parent_id,
                task_type,
                depth,
                json.dumps(payload, ensure_ascii=False),
                idempotency_key,
                timeout_seconds,
                limits.max_retries,
            ),
        )
    return get_subtask(task_id, database_path=database_path)


def run_pending_subtasks(
    handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]],
    *,
    parent_id: str,
    database_path: str | os.PathLike[str] | None = None,
    limits: SubtaskLimits = SubtaskLimits(),
) -> list[dict[str, Any]]:
    tasks = list_subtasks(parent_id, status="pending", database_path=database_path)

    def execute(task: dict[str, Any]) -> None:
        with connect(database_path) as database:
            database.execute(
                "UPDATE agent_subtasks SET status='running', started_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
                (task["id"],),
            )
        handler = handlers.get(task["task_type"])
        if handler is None:
            _finish(task["id"], "failed", error="subtask_handler_not_found", database_path=database_path)
            return
        try:
            result = handler(task["payload"])
        except Exception as exc:
            _finish(task["id"], "failed", error=str(exc), database_path=database_path)
        else:
            _finish(task["id"], "completed", result=result, database_path=database_path)

    with ThreadPoolExecutor(max_workers=max(1, limits.max_concurrency)) as executor:
        futures = [executor.submit(execute, task) for task in tasks]
        for future in as_completed(futures):
            future.result()
    return list_subtasks(parent_id, database_path=database_path)


def cancel_subtask(
    task_id: str,
    *,
    database_path: str | os.PathLike[str] | None = None,
) -> bool:
    with connect(database_path) as database:
        cursor = database.execute(
            """
            UPDATE agent_subtasks
            SET status='cancelled', finished_at=CURRENT_TIMESTAMP
            WHERE id=? AND status='pending'
            """,
            (task_id,),
        )
    return cursor.rowcount == 1


def get_subtask(
    task_id: str,
    *,
    database_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    with connect(database_path) as database:
        row = database.execute(
            "SELECT * FROM agent_subtasks WHERE id = ?", (task_id,)
        ).fetchone()
    if row is None:
        raise KeyError(task_id)
    return _decode(dict(row))


def list_subtasks(
    parent_id: str,
    *,
    status: str | None = None,
    database_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    initialize(database_path)
    query = "SELECT * FROM agent_subtasks WHERE parent_id = ?"
    params: list[object] = [parent_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at, id"
    with connect(database_path) as database:
        rows = database.execute(query, params).fetchall()
    return [_decode(dict(row)) for row in rows]


def _finish(
    task_id: str,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    database_path: str | os.PathLike[str] | None,
) -> None:
    with connect(database_path) as database:
        database.execute(
            """
            UPDATE agent_subtasks
            SET status=?, result=?, error_message=?, finished_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error[:1000] if error else None,
                task_id,
            ),
        )


def _decode(task: dict[str, Any]) -> dict[str, Any]:
    task["payload"] = json.loads(task["payload"])
    task["result"] = json.loads(task["result"]) if task.get("result") else None
    return task
