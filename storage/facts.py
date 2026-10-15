"""Repository for source-backed lifestyle facts."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from typing import Any

from .sqlite import connect, initialize


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def record_lifestyle_fact(
    *,
    message_id: str,
    category: str,
    text: str,
    image_paths: list[str] | tuple[str, ...] = (),
    recorded_at: dt.datetime | None = None,
    database_path: str | None = None,
) -> str:
    """Persist one source-backed fact without treating Agent estimates as truth."""
    initialize(database_path)
    source_id = f"feishu:{message_id}"
    fact_id = _stable_id("lifestyle", message_id)
    timestamp = (recorded_at or dt.datetime.now()).isoformat(timespec="seconds")
    source_payload = {
        "message_id": message_id,
        "category": category,
        "text": text,
        "image_paths": list(image_paths),
    }
    payload = {
        "category": category,
        "text": text,
        "image_paths": list(image_paths),
        "estimated": False,
    }
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO source_records
              (id, source_type, source_path, recorded_at, raw_payload)
            VALUES (?, 'feishu_message', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              source_path=excluded.source_path,
              recorded_at=excluded.recorded_at,
              raw_payload=excluded.raw_payload
            """,
            (
                source_id,
                image_paths[0] if image_paths else None,
                timestamp,
                json.dumps(source_payload, ensure_ascii=False),
            ),
        )
        connection.execute(
            """
            INSERT INTO fact_records
              (id, fact_type, source_id, recorded_at, payload, confidence)
            VALUES (?, 'lifestyle_record', ?, ?, ?, 1.0)
            ON CONFLICT(id) DO UPDATE SET
              payload=excluded.payload,
              recorded_at=excluded.recorded_at,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                fact_id,
                source_id,
                timestamp,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    return fact_id


def get_fact(
    fact_id: str,
    *,
    database_path: str | None = None,
) -> dict[str, Any] | None:
    initialize(database_path)
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM fact_records WHERE id = ?", (fact_id,)
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["payload"] = json.loads(result["payload"])
    return result
