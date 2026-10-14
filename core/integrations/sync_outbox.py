"""Durable journal for cross-system synchronization attempts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

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
                updated_at TEXT NOT NULL
            )
            """
        )
        return connection

    def _ensure_schema(self):
        with self._connect() as connection:
            connection.commit()

    def begin(self, key: str, kind: str, payload: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_outbox(key, kind, payload_json, status, attempts, updated_at)
                VALUES (?, ?, ?, 'pending', 1, ?)
                ON CONFLICT(key) DO UPDATE SET
                    status = CASE
                        WHEN sync_outbox.status = 'succeeded' THEN 'succeeded'
                        ELSE 'pending'
                    END,
                    attempts = sync_outbox.attempts + 1,
                    updated_at = excluded.updated_at
                """,
                (key, kind, json.dumps(payload, ensure_ascii=False), now),
            )
            connection.commit()

    def finish(self, key: str, success: bool, error: str = "") -> None:
        status = "succeeded" if success else "failed"
        with self._connect() as connection:
            connection.execute(
                "UPDATE sync_outbox SET status = ?, last_error = ?, updated_at = ? WHERE key = ?",
                (status, error[:500], datetime.now(timezone.utc).isoformat(), key),
            )
            connection.commit()

    def pending(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT key, kind, payload_json, status, attempts, last_error, updated_at
                FROM sync_outbox
                WHERE status != 'succeeded'
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "key": row[0], "kind": row[1], "payload": json.loads(row[2]),
                "status": row[3], "attempts": row[4], "last_error": row[5],
                "updated_at": row[6],
            }
            for row in rows
        ]


sync_outbox = SyncOutbox()
