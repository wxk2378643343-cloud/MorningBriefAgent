"""Small structured logging helpers shared by adapters and services."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from typing import Callable, Iterator
from functools import wraps


_SENSITIVE_PATTERNS = (
    re.compile(
        r"(?i)(access_key|ticket|csrf_token|app_secret)=([^&\s]+)"
    ),
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s,;]+)"),
)


def redact_sensitive_text(value: object) -> str:
    """Redact known credential forms before they reach persistent logs."""
    text = str(value)
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.groups == 2:
            text = pattern.sub(r"\1=<redacted>", text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Apply credential redaction to a fully rendered log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive_text(record.getMessage())
        record.args = ()
        return True


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
