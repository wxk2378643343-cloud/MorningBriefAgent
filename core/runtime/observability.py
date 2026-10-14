"""Small structured logging helpers shared by adapters and services."""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Callable, Iterator
from functools import wraps


def correlation_id() -> str:
    return uuid.uuid4().hex[:12]


def event(logger: logging.Logger, name: str, **fields) -> None:
    payload = {"event": name, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))


@contextmanager
def timed(logger: logging.Logger, operation: str, correlation: str = "") -> Iterator[str]:
    request_id = correlation or correlation_id()
    started = time.perf_counter()
    try:
        yield request_id
    except Exception as exc:
        event(
            logger, "integration_failed", operation=operation,
            correlation_id=request_id, elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
        )
        raise
    else:
        event(
            logger, "integration_succeeded", operation=operation,
            correlation_id=request_id, elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )


def traced(logger: logging.Logger, operation: str) -> Callable:
    """Decorate a synchronous boundary with structured timing events."""
    def decorator(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with timed(logger, operation):
                return function(*args, **kwargs)
        return wrapped
    return decorator
