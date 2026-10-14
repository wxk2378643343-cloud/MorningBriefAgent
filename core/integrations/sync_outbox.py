"""Durable journal for cross-system synchronization attempts."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from ..runtime import config
except ImportError:
    from core.runtime import config

from .feishu.idempotency import IdempotencyStore


class SyncOutbox:
    """Records desired side effects so failed work is visible and replayable.

    The actual provider call remains in the application service and is
    protected by the idempotency store. This journal supplies durable intent
    and status for reconciliation after a partial multi-system write.
    """

    def __init__(self, store: IdempotencyStore | None = None):
        self.store = store or IdempotencyStore()
        self.path = self.store.path
        self._ensure_schema()

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_outbox (
                key TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                next_retry_at TEXT,
                lease_owner TEXT,
                lease_until TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(sync_outbox)").fetchall()
        }
        if "next_retry_at" not in columns:
            connection.execute("ALTER TABLE sync_outbox ADD COLUMN next_retry_at TEXT")
        if "lease_owner" not in columns:
            connection.execute("ALTER TABLE sync_outbox ADD COLUMN lease_owner TEXT")
        if "lease_until" not in columns:
            connection.execute("ALTER TABLE sync_outbox ADD COLUMN lease_until TEXT")
        return connection

    def _ensure_schema(self):
        with closing(self._connect()) as connection:
            connection.commit()

    def begin(
        self,
        key: str,
        kind: str,
        payload: dict[str, Any],
        *,
        lease_seconds: int | None = None,
    ) -> str:
        """Record and lease one immediate delivery attempt."""
        owner = uuid.uuid4().hex
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lease_until = (
            now_dt + timedelta(
                seconds=max(
                    1,
                    config.OUTBOX_LEASE_SECONDS
                    if lease_seconds is None else lease_seconds,
                )
            )
        ).isoformat()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO sync_outbox(
                    key, kind, payload_json, status, attempts,
                    lease_owner, lease_until, updated_at
                )
                VALUES (?, ?, ?, 'inflight', 1, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    kind = excluded.kind,
                    payload_json = excluded.payload_json,
                    status = CASE
                        WHEN sync_outbox.status = 'succeeded' THEN 'succeeded'
                        ELSE 'inflight'
                    END,
                    attempts = CASE
                        WHEN sync_outbox.status = 'succeeded'
                            THEN sync_outbox.attempts
                        ELSE sync_outbox.attempts + 1
                    END,
                    last_error = NULL,
                    next_retry_at = NULL,
                    lease_owner = CASE
                        WHEN sync_outbox.status = 'succeeded'
                            THEN NULL
                        ELSE excluded.lease_owner
                    END,
                    lease_until = CASE
                        WHEN sync_outbox.status = 'succeeded'
                            THEN NULL
                        ELSE excluded.lease_until
                    END,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    kind,
                    json.dumps(payload, ensure_ascii=False),
                    owner,
                    lease_until,
                    now,
                ),
            )
            connection.commit()
        return owner

    def finish(
        self,
        key: str,
        success: bool,
        error: str = "",
        *,
        lease_owner: str | None = None,
    ) -> bool:
        """Finish a leased attempt; stale workers cannot overwrite new work."""
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, attempts, lease_owner FROM sync_outbox WHERE key = ?",
                (key,),
            ).fetchone()
            if not row:
                connection.rollback()
                return False
            current_status, attempts, current_owner = row
            if success and current_status == "succeeded":
                connection.commit()
                return True
            if lease_owner and current_owner != lease_owner:
                connection.rollback()
                return False

            if success:
                cursor = connection.execute(
                    """
                    UPDATE sync_outbox
                    SET status = 'succeeded', last_error = NULL,
                        next_retry_at = NULL, lease_owner = NULL,
                        lease_until = NULL, updated_at = ?
                    WHERE key = ?
                    """,
                    (datetime.now(timezone.utc).isoformat(), key),
                )
                connection.commit()
                return cursor.rowcount == 1

            attempts = int(attempts)
            max_attempts = max(1, config.OUTBOX_MAX_ATTEMPTS)
            status = "dead_letter" if attempts >= max_attempts else "failed"
            delays = config.OUTBOX_RETRY_DELAYS_SECONDS or (300,)
            delay = delays[min(max(attempts - 1, 0), len(delays) - 1)]
            next_retry = (
                None
                if status == "dead_letter"
                else datetime.now(timezone.utc).timestamp() + max(0, delay)
            )
            connection.execute(
                """
                UPDATE sync_outbox
                SET status = ?, last_error = ?, next_retry_at = ?, updated_at = ?
                    , lease_owner = NULL, lease_until = NULL
                WHERE key = ?
                """,
                (
                    status,
                    error[:500],
                    (
                        datetime.fromtimestamp(next_retry, timezone.utc).isoformat()
                        if next_retry is not None else None
                    ),
                    datetime.now(timezone.utc).isoformat(),
                    key,
                ),
            )
            connection.commit()
            return True

    def claim_due(
        self,
        limit: int = 100,
        *,
        lease_seconds: int | None = None,
    ) -> list[dict[str, Any]]:
        """Atomically lease due records and increment their real attempt count."""
        owner = uuid.uuid4().hex
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lease_until = (
            now_dt + timedelta(
                seconds=max(
                    1,
                    config.OUTBOX_LEASE_SECONDS
                    if lease_seconds is None else lease_seconds,
                )
            )
        ).isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT key, kind, payload_json, status, attempts, last_error,
                       next_retry_at, updated_at
                FROM sync_outbox
                WHERE (
                    status IN ('pending', 'failed')
                    AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ) OR (
                    status = 'inflight'
                    AND lease_until IS NOT NULL
                    AND lease_until <= ?
                )
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (now, now, limit),
            ).fetchall()
            keys = [row[0] for row in rows]
            for key in keys:
                connection.execute(
                    """
                    UPDATE sync_outbox
                    SET status = 'inflight', attempts = attempts + 1,
                        lease_owner = ?, lease_until = ?, updated_at = ?
                    WHERE key = ?
                    """,
                    (owner, lease_until, now, key),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return [
            {
                "key": row[0],
                "kind": row[1],
                "payload": json.loads(row[2]),
                "status": "inflight",
                "attempts": int(row[4]) + 1,
                "last_error": row[5],
                "next_retry_at": row[6],
                "updated_at": now,
                "lease_owner": owner,
                "lease_until": lease_until,
            }
            for row in rows
        ]

    def pending(self, limit: int = 100) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT key, kind, payload_json, status, attempts, last_error,
                       next_retry_at, updated_at
                FROM sync_outbox
                WHERE (
                    status IN ('pending', 'failed')
                    AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ) OR (
                    status = 'inflight'
                    AND lease_until IS NOT NULL
                    AND lease_until <= ?
                )
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (now, now, limit),
            ).fetchall()
        return [
            {
                "key": row[0], "kind": row[1], "payload": json.loads(row[2]),
                "status": row[3], "attempts": row[4], "last_error": row[5],
                "next_retry_at": row[6], "updated_at": row[7],
            }
            for row in rows
        ]

    def dead_letter(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT key, kind, payload_json, status, attempts, last_error,
                       next_retry_at, updated_at
                FROM sync_outbox
                WHERE status = 'dead_letter'
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "key": row[0], "kind": row[1], "payload": json.loads(row[2]),
                "status": row[3], "attempts": row[4], "last_error": row[5],
                "next_retry_at": row[6], "updated_at": row[7],
            }
            for row in rows
        ]

    def purge_succeeded(self, retention_days: int | None = None) -> int:
        """Delete only old successful records; pending failures are untouched."""
        days = (
            config.OUTBOX_SUCCESS_RETENTION_DAYS
            if retention_days is None else max(0, retention_days)
        )
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "DELETE FROM sync_outbox WHERE status = 'succeeded' AND updated_at < ?",
                (cutoff_iso,),
            )
            connection.commit()
            return cursor.rowcount


sync_outbox = SyncOutbox()
