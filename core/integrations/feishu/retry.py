"""Small dependency-free retry helper."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from integration_errors import RetryableIntegrationError

T = TypeVar("T")


def retry_call(operation: Callable[[], T], attempts: int = 3, delay: float = 0.25) -> T:
    last_error = None
    for attempt in range(attempts):
        try:
            return operation()
        except RetryableIntegrationError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(delay * (2 ** attempt))
    if last_error:
        raise last_error
    raise RuntimeError("retry operation did not execute")
