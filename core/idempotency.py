"""SQLite-backed idempotency store for local side effects."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

try:
    from . import config
except ImportError:
    import config


def make_key(namespace: str, *parts: object) -> str:
    raw = "\x1f".join([namespace, *(str(part).strip() for part in parts)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotencyStore:
    """Transactional store for one local application.

    SQLite gives atomic upserts and survives process restarts. The primary key
    prevents duplicate records even when multiple local workers are active.
    """

    def __init__(self, path: os.PathLike[str] | str | None = None):
        self.path = Path(path or config.IDEMPOTENCY_STORE_PATH)
        self._lock = threading.RLock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.commit()

    def get(self, key: str) -> Optional[Any]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM idempotency WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    def put(self, key: str, value: Any) -> None:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO idempotency(key, value_json)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, encoded),
            )
            connection.commit()


store = IdempotencyStore()
