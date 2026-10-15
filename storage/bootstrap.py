"""Local-first workspace bootstrap used by the future desktop onboarding flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from storage.sqlite import connect, initialize


WORKSPACE_DIRECTORIES = (
    "knowledge/profile",
    "knowledge/briefings",
    "knowledge/notes",
    "knowledge/reviews",
    "knowledge/archive",
    "conversations",
    "attachments",
    "logs",
    "cache",
    "outbox",
)


def initialize_workspace(
    workspace_root: str | Path,
    *,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create local directories and record setup state without touching user data."""
    root = Path(workspace_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    created_directories: list[str] = []
    for relative in WORKSPACE_DIRECTORIES:
        directory = root / relative
        if not directory.exists():
            directory.mkdir(parents=True)
            created_directories.append(relative)

    database = initialize(database_path)
    with connect(database) as connection:
        connection.execute(
            """
            INSERT INTO installation_state (id, workspace_root)
            VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET
              workspace_root=excluded.workspace_root,
              updated_at=CURRENT_TIMESTAMP
            """,
            (str(root),),
        )
    return {
        "workspace_root": str(root),
        "database_path": str(database),
        "created_directories": created_directories,
    }


def get_installation_state(
    database_path: str | Path | None = None,
) -> dict[str, Any] | None:
    initialize(database_path)
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM installation_state WHERE id = 1"
        ).fetchone()
    return dict(row) if row else None


def mark_setup_complete(
    *,
    provider: str,
    channel: str,
    database_path: str | Path | None = None,
) -> None:
    initialize(database_path)
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO installation_state
              (id, completed, selected_provider, selected_channel, completed_at)
            VALUES (1, 1, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
              completed=1,
              selected_provider=excluded.selected_provider,
              selected_channel=excluded.selected_channel,
              completed_at=CURRENT_TIMESTAMP,
              updated_at=CURRENT_TIMESTAMP
            """,
            (provider, channel),
        )
