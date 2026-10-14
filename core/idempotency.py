"""SQLite-backed idempotency store for local side effects."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from collections.abc import Callable
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
        self.legacy_path = self.path.with_suffix(".json")
        self._lock = threading.RLock()
        self._ensure_schema()
        self._migrate_legacy_json()

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

    def _migrate_legacy_json(self) -> None:
        """Import the previous JSON store once, without deleting user data."""
        if self.legacy_path == self.path or not self.legacy_path.is_file():
            return
        try:
            legacy = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(legacy, dict):
            return
        with self._lock, self._connect() as connection:
            for key, value in legacy.items():
                connection.execute(
                    """
                    INSERT OR IGNORE INTO idempotency(key, value_json)
                    VALUES (?, ?)
                    """,
                    (str(key), json.dumps(value, ensure_ascii=False, separators=(",", ":"))),
                )
            connection.commit()
        # Keep the ignored legacy file as a recoverable backup and write a
        # marker so startup does not repeatedly scan it.
        marker = self.legacy_path.with_suffix(".json.migrated")
        try:
            marker.write_text("migrated to SQLite\n", encoding="utf-8")
        except OSError:
            pass

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

    def execute_once(
        self,
        key: str,
        operation: Callable[[], Any],
        success: Callable[[Any], bool] = bool,
    ) -> tuple[Any, bool]:
        """Run a side effect once and return ``(result, reused)``.

        Pending and failed records remain retryable. A successful record is
        reused, which centralizes the same check/execute/save pattern for
        tasks, calendar events, and cards.
        """
        existing = self.get(key)
        if isinstance(existing, dict) and existing.get("status") == "succeeded":
            return existing.get("result"), True

        self.put(key, {"status": "pending", "attempts": self._attempts(existing) + 1})
        try:
            result = operation()
            if success(result):
                self.put(key, {"status": "succeeded", "result": result})
            else:
                self.put(key, {"status": "failed", "result": result})
            return result, False
        except Exception as exc:
            self.put(key, {
                "status": "failed",
                "error": type(exc).__name__,
                "message": str(exc)[:300],
            })
            raise

    @staticmethod
    def _attempts(value: Any) -> int:
        return int(value.get("attempts", 0)) if isinstance(value, dict) else 0


store = IdempotencyStore()
