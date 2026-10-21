"""Repository for agent_requests table managing request lifecycle and audit state."""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any, Optional

from storage.sqlite import connect, initialize, insert_audit


REQUEST_VALID_STATUSES = {
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
}


def create_agent_request(
    *,
    source_message_id: str,
    prompt: str,
    context: str = "",
    request_kind: str = "conversation",
    provider: str = "agy",
    database_path: str | None = None,
) -> tuple[str, bool]:
    """Idempotently create an agent request for (source_message_id, request_kind).

    Returns:
        (request_id, is_new)
        If the request already exists, returns existing (request_id, False).
    """
    initialize(database_path)
    with connect(database_path) as connection:
        # Check existing first
        row = connection.execute(
            """
            SELECT request_id, status FROM agent_requests
            WHERE source_message_id = ? AND request_kind = ?
            """,
            (source_message_id, request_kind),
        ).fetchone()
        if row:
            return str(row["request_id"]), False

        request_id = f"req_{uuid.uuid4().hex[:16]}"
        try:
            connection.execute(
                """
                INSERT INTO agent_requests
                  (request_id, source_message_id, request_kind, provider, status, prompt, context)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (request_id, source_message_id, request_kind, provider, prompt, context),
            )
            insert_audit(
                connection,
                entity_type="agent_request",
                entity_id=request_id,
                action="create_request",
                actor=f"feishu:{source_message_id}",
                after_value={"status": "pending", "provider": provider},
            )
            return request_id, True
        except sqlite3.IntegrityError:
            # Race condition: another thread inserted between SELECT and INSERT
            row = connection.execute(
                """
                SELECT request_id FROM agent_requests
                WHERE source_message_id = ? AND request_kind = ?
                """,
                (source_message_id, request_kind),
            ).fetchone()
            if row:
                return str(row["request_id"]), False
            raise


def attach_reply_message_id(
    request_id: str,
    reply_message_id: str,
    *,
    database_path: str | None = None,
) -> bool:
    """Associate the Feishu progress reply card ID with the request."""
    initialize(database_path)
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE agent_requests
            SET reply_message_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE request_id = ?
            """,
            (reply_message_id, request_id),
        )
        return cursor.rowcount > 0


def mark_request_running(
    request_id: str,
    *,
    database_path: str | None = None,
) -> bool:
    """Atomic transition: pending -> running."""
    initialize(database_path)
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE agent_requests
            SET status = 'running',
                started_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE request_id = ? AND status = 'pending'
            """,
            (request_id,),
        )
        if cursor.rowcount > 0:
            insert_audit(
                connection,
                entity_type="agent_request",
                entity_id=request_id,
                action="status_running",
                actor="system",
                before_value="pending",
                after_value="running",
            )
            return True
        return False


def mark_request_completed(
    request_id: str,
    result_text: str,
    *,
    database_path: str | None = None,
) -> bool:
    """Atomic transition: running -> completed.

    If status is no longer 'running' (e.g. cancelled by user recall),
    rowcount will be 0 and caller MUST drop the result!
    """
    initialize(database_path)
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE agent_requests
            SET status = 'completed',
                result_text = ?,
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE request_id = ? AND status = 'running'
            """,
            (result_text, request_id),
        )
        if cursor.rowcount > 0:
            insert_audit(
                connection,
                entity_type="agent_request",
                entity_id=request_id,
                action="status_completed",
                actor="system",
                before_value="running",
                after_value="completed",
            )
            return True
        return False


def mark_request_failed(
    request_id: str,
    error_message: str,
    *,
    database_path: str | None = None,
) -> bool:
    """Atomic transition: running -> failed."""
    initialize(database_path)
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE agent_requests
            SET status = 'failed',
                error = ?,
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE request_id = ? AND status = 'running'
            """,
            (error_message, request_id),
        )
        if cursor.rowcount > 0:
            insert_audit(
                connection,
                entity_type="agent_request",
                entity_id=request_id,
                action="status_failed",
                actor="system",
                before_value="running",
                after_value="failed",
            )
            return True
        return False


def mark_request_cancelled(
    request_id: str,
    *,
    actor: str = "user_recall",
    database_path: str | None = None,
) -> bool:
    """Atomic transition: (pending | running) -> cancelled.

    Terminal states (completed, failed, cancelled, interrupted) are NEVER overwritten.
    """
    initialize(database_path)
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE agent_requests
            SET status = 'cancelled',
                cancel_requested_at = CURRENT_TIMESTAMP,
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE request_id = ? AND status IN ('pending', 'running')
            """,
            (request_id,),
        )
        if cursor.rowcount > 0:
            insert_audit(
                connection,
                entity_type="agent_request",
                entity_id=request_id,
                action="status_cancelled",
                actor=actor,
                before_value="active",
                after_value="cancelled",
            )
            return True
        return False


def cancel_by_source_message(
    source_message_id: str,
    *,
    actor: str = "user_recall",
    database_path: str | None = None,
) -> list[str]:
    """Find and cancel all active requests for a source_message_id.

    Returns list of cancelled request_ids.
    """
    initialize(database_path)
    cancelled_ids = []
    with connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT request_id FROM agent_requests
            WHERE source_message_id = ? AND status IN ('pending', 'running')
            """,
            (source_message_id,),
        ).fetchall()
        for row in rows:
            req_id = str(row["request_id"])
            if mark_request_cancelled(req_id, actor=actor, database_path=database_path):
                cancelled_ids.append(req_id)
    return cancelled_ids


def recover_interrupted_requests(*, database_path: str | None = None) -> int:
    """Called on startup: clean up any dangling 'running' requests into 'interrupted'."""
    initialize(database_path)
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE agent_requests
            SET status = 'interrupted',
                error = 'server_restarted_during_execution',
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'running'
            """
        )
        count = cursor.rowcount
        if count > 0:
            insert_audit(
                connection,
                entity_type="agent_request",
                entity_id="bulk_recovery",
                action="status_interrupted",
                actor="startup_recovery",
                after_value={"interrupted_count": count},
            )
        return count


def get_agent_request(
    request_id: str,
    *,
    database_path: str | None = None,
) -> Optional[dict[str, Any]]:
    """Retrieve an agent request record by ID."""
    initialize(database_path)
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM agent_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return dict(row) if row else None
