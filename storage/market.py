"""Repositories for fund market observations and news source records."""

from __future__ import annotations

import hashlib
from typing import Any

from .sqlite import connect, initialize


def _ensure_source(connection, source_id: str) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO source_records
          (id, source_type, recorded_at)
        VALUES (?, 'structured_input', CURRENT_TIMESTAMP)
        """,
        (source_id,),
    )


def save_fund_snapshot(
    *,
    fund_code: str,
    price: float | None,
    change_percent: float | None,
    market_time: str,
    data_source: str,
    is_realtime: bool = False,
    database_path: str | None = None,
) -> int:
    initialize(database_path)
    with connect(database_path) as connection:
        _ensure_source(connection, data_source)
        cursor = connection.execute(
            """
            INSERT INTO fund_market_snapshots
              (fund_code, price, change_percent, market_time, data_source, is_realtime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fund_code, price, change_percent, market_time,
                data_source, int(is_realtime),
            ),
        )
        return int(cursor.lastrowid)


def save_news_item(
    *,
    title: str,
    source_id: str,
    category: str,
    url: str = "",
    published_at: str | None = None,
    summary: str = "",
    database_path: str | None = None,
) -> str:
    initialize(database_path)
    news_id = "news:" + hashlib.sha256(
        f"{url}|{title}".encode("utf-8")
    ).hexdigest()[:24]
    with connect(database_path) as connection:
        _ensure_source(connection, source_id)
        connection.execute(
            """
            INSERT INTO news_items
              (id, source_id, title, url, published_at, category, summary, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              summary=excluded.summary,
              published_at=excluded.published_at,
              content_hash=excluded.content_hash
            """,
            (
                news_id, source_id, title, url, published_at, category, summary,
                hashlib.sha256(summary.encode("utf-8")).hexdigest(),
            ),
        )
    return news_id
