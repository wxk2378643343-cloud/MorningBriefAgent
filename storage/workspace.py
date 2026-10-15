"""Local workspace bootstrap and non-secret desktop settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from storage.sqlite import connect, initialize

WORKSPACE_DIRECTORIES = (
    "data",
    "vault",
    "logs",
    "attachments",
    "conversations",
    "exports",
    "config",
)


def initialize_workspace(root_path: str | Path, *, database_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(root_path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    for directory in WORKSPACE_DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)
    database = root / "data" / "app.sqlite3"
    initialize(database)
    metadata_database = Path(database_path) if database_path else database
    initialize(metadata_database)
    with connect(metadata_database) as connection:
        connection.execute(
            """
            INSERT INTO installation_state (id, setup_version, workspace_root)
            VALUES (1, 1, ?)
            ON CONFLICT(id) DO UPDATE SET
              workspace_root=excluded.workspace_root,
              updated_at=CURRENT_TIMESTAMP
            """,
            (str(root),),
        )
        _set_setting(connection, "workspace_root", str(root))
        _set_setting(connection, "workspace_database", str(database))
        _set_setting(connection, "workspace_vault", str(root / "vault"))
    return workspace_info(metadata_database)


def workspace_info(database_path: str | Path | None = None) -> dict[str, Any]:
    database = initialize(database_path)
    with connect(database) as connection:
        row = connection.execute(
            "SELECT workspace_root FROM installation_state WHERE id = 1"
        ).fetchone()
    root = Path(str(row["workspace_root"])).resolve() if row and row["workspace_root"] else None
    return {
        "configured": bool(root and root.is_dir()),
        "root_path": str(root) if root else None,
        "database_path": str(root / "data" / "app.sqlite3") if root else str(database),
        "vault_path": str(root / "vault") if root else None,
        "directories": [str(root / item) for item in WORKSPACE_DIRECTORIES] if root else [],
    }


def save_personal_context(
    values: dict[str, str],
    *,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    info = workspace_info(database_path)
    if not info["configured"]:
        raise ValueError("workspace_not_configured")
    target = Path(str(info["vault_path"])) / "个人上下文.md"
    content = "# 个人上下文\n\n"
    for key, value in values.items():
        if str(value).strip():
            content += f"## {key}\n\n{str(value).strip()}\n\n"
    target.write_text(content, encoding="utf-8")
    with connect(database_path) as connection:
        _set_setting(connection, "profile_path", str(target))
    return {"path": str(target), "updated": target.stat().st_mtime}


def _set_setting(connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO local_settings (key, value, is_secret)
        VALUES (?, ?, 0)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,
          updated_at=CURRENT_TIMESTAMP
        """,
        (key, json.dumps(value, ensure_ascii=False)),
    )
