"""Small SQLite bootstrap layer; business services use repositories above it."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.runtime import config


SCHEMA_VERSION = 1


class ManagedConnection(sqlite3.Connection):
    """Close SQLite handles when used in a ``with connect(...)`` block."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    database = Path(path or config.SQLITE_DATABASE_PATH)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, factory=ManagedConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize(
    path: str | Path | None = None,
    *,
    demo: bool = False,
) -> Path:
    database = Path(
        path
        or (
            config.DEMO_SQLITE_DATABASE_PATH
            if demo else config.SQLITE_DATABASE_PATH
        )
    )
    with connect(database) as connection:
        connection.executescript(
            (Path(__file__).with_name("schema.sql")).read_text(
                encoding="utf-8"
            )
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
    return database


def insert_audit(
    connection: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str,
    before_value: Any = None,
    after_value: Any = None,
) -> None:
    import json

    connection.execute(
        """
        INSERT INTO audit_log
        (entity_type, entity_id, action, before_value, after_value, actor)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            entity_type,
            entity_id,
            action,
            json.dumps(before_value, ensure_ascii=False, default=str)
            if before_value is not None else None,
            json.dumps(after_value, ensure_ascii=False, default=str)
            if after_value is not None else None,
            actor,
        ),
    )
