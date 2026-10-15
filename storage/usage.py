"""Persistence for Agent token usage and provider execution metadata."""

from __future__ import annotations

import time
import uuid
import threading
from typing import Any

from .sqlite import connect, initialize

_LAST_USAGE = threading.local()


def estimate_tokens(text: str) -> int:
    """Conservative, provider-neutral estimate for local AGY calls."""
    return max(1, (len(text or "") + 3) // 4)


def record_usage(
    *,
    task: str,
    provider: str,
    input_tokens: int | None,
    output_tokens: int | None,
    token_source: str = "estimated",
    duration_ms: int | None = None,
    status: str = "success",
    request_id: str | None = None,
    database_path: str | None = None,
) -> str:
    initialize(database_path)
    request_id = request_id or uuid.uuid4().hex
    total = None
    if input_tokens is not None or output_tokens is not None:
        total = (input_tokens or 0) + (output_tokens or 0)
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO agent_usage_records
            (request_id, task, provider, input_tokens, output_tokens,
             total_tokens, token_source, duration_ms, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (request_id, task, provider, input_tokens, output_tokens, total,
             token_source, duration_ms, status),
        )
    _LAST_USAGE.value = {
        "provider": provider,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "token_source": token_source,
    }
    return request_id


def get_last_usage() -> dict[str, Any] | None:
    """Return usage for the current worker thread's latest Agent call."""
    return getattr(_LAST_USAGE, "value", None)


def clear_last_usage() -> None:
    _LAST_USAGE.value = None


def usage_summary(*, database_path: str | None = None) -> dict[str, Any]:
    initialize(database_path)
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS requests,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM agent_usage_records
            """
        ).fetchone()
    return dict(row)


class UsageTimer:
    def __init__(self) -> None:
        self.started = time.perf_counter()

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)
