"""Small file-backed idempotency store for side-effecting integrations."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

try:
    from . import config
except ImportError:
    import config


def make_key(namespace: str, *parts: object) -> str:
    """Create a stable, non-sensitive key from business identity fields."""
    raw = "\x1f".join([namespace, *(str(part).strip() for part in parts)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotencyStore:
    """JSON store suitable for the single local worker process.

    Writes use replace semantics so a process interruption cannot leave a
    half-written JSON document. The store contains only provider IDs and
    hashes, never message bodies or credentials.
    """

    def __init__(self, path: os.PathLike[str] | str | None = None):
        self.path = Path(path or config.IDEMPOTENCY_STORE_PATH)
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._read().get(key)

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            data = self._read()
            data[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False, indent=2)
                os.replace(temp_name, self.path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)


store = IdempotencyStore()
