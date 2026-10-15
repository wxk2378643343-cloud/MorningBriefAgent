"""Repositories for fund positions, market observations, and news records."""

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


def save_fund_position(
    *,
    fund_code: str,
    fund_name: str = "",
    shares: float | None = None,
    cost_price: float | None = None,
    source_id: str,
    recorded_at: str,
    database_path: str | None = None,
) -> str:
    """Persist one dated private holding snapshot idempotently."""
    initialize(database_path)
    position_id = "fund-position:" + hashlib.sha256(
        f"{fund_code}|{recorded_at[:10]}".encode("utf-8")
    ).hexdigest()[:24]
    with connect(database_path) as connection:
        _ensure_source(connection, source_id)
        connection.execute(
            """
            INSERT INTO fund_records
              (id, fund_code, fund_name, shares, cost_price, source_id, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              fund_name=excluded.fund_name,
              shares=excluded.shares,
              cost_price=excluded.cost_price,
              source_id=excluded.source_id,
              recorded_at=excluded.recorded_at
            """,
            (
                position_id, fund_code, fund_name, shares, cost_price,
                source_id, recorded_at,
            ),
        )
    return position_id


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
