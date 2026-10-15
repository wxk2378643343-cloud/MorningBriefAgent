"""System credential storage boundary for desktop secrets."""

from __future__ import annotations

import os

SERVICE_NAME = "MorningBriefAgent"


def set_secret(name: str, value: str) -> None:
    if not value:
        raise ValueError("secret_required")
    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError("keyring_dependency_missing") from exc
    keyring.set_password(SERVICE_NAME, name, value)


def get_secret(name: str) -> str | None:
    try:
        import keyring
    except ImportError:
        return os.getenv(name)
    return keyring.get_password(SERVICE_NAME, name)
