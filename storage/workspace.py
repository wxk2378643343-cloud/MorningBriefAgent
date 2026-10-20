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

OBSIDIAN_LAYOUT = {
    "00-首页.md": "# MorningBrief 本地工作台\n\n这是你的本地 Agent 知识库入口。\n\n- [[01-今日计划/README]]\n- [[02-待办/README]]\n- [[03-日程/README]]\n- [[04-新闻简报/README]]\n- [[05-知识库/README]]\n- [[06-聊天复盘/README]]\n- [[07-饮食记录/README]]\n- [[08-运动记录/README]]\n- [[09-基金投资/README]]\n- [[99-归档/README]]\n",
    "01-今日计划/README.md": "# 今日计划\n\n记录每日计划、重点和复盘入口。\n",
    "02-待办/README.md": "# 待办\n\nAgent 整理的待办事项会写入这里。\n",
    "03-日程/README.md": "# 日程\n\n记录确认后的日程和时间安排。\n",
    "04-新闻简报/README.md": "# 新闻简报\n\n定时新闻分析和晨报会归档到这里。\n",
    "05-知识库/README.md": "# 知识库\n\n放置你的 Markdown、学习资料和长期上下文。\n",
    "06-聊天复盘/README.md": "# 聊天复盘\n\n记录 Agent 对聊天和工作内容的复盘结果。\n",
    "07-饮食记录/README.md": "# 饮食记录\n\n记录饮食、热量和营养数据。\n",
    "08-运动记录/README.md": "# 运动记录\n\n记录训练、运动和身体状态。\n",
    "09-基金投资/README.md": "# 基金投资\n\n记录基金、股票和投资分析结果。\n",
    "99-归档/README.md": "# 归档\n\n存放已经完成或不再活跃的内容。\n",
}

def default_workspace_root() -> Path:
    """Return a safe local default without requiring a cloud or user prompt."""
    preferred = Path("D:/MorningBriefWorkspace")
    return preferred if Path("D:/").is_dir() else Path.home() / "MorningBriefWorkspace"


def initialize_workspace(root_path: str | Path, *, database_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(root_path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    for directory in WORKSPACE_DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)
    vault = root / "vault"
    created_files: list[str] = []
    for relative_path, content in OBSIDIAN_LAYOUT.items():
        target = vault / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(content, encoding="utf-8")
            created_files.append(str(target))
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
    result = workspace_info(metadata_database)
    result["created_files"] = created_files
    return result


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
        "default_root_path": str(default_workspace_root()),
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
    display_name = str(values.get("display_name", "")).strip()
    if len(display_name) > 40:
        raise ValueError("display_name_too_long")
    target = Path(str(info["vault_path"])) / "个人上下文.md"
    context_values = {
        key: str(value).strip()
        for key, value in values.items()
        if key != "display_name" and str(value).strip()
    }
    if context_values:
        content = "# 个人上下文\n\n"
        for key, value in context_values.items():
            content += f"## {key}\n\n{value}\n\n"
        target.write_text(content, encoding="utf-8")
    with connect(database_path) as connection:
        if target.is_file():
            _set_setting(connection, "profile_path", str(target))
        if display_name:
            _set_setting(connection, "user_display_name", display_name)
    return {
        "path": str(target) if target.is_file() else None,
        "updated": target.stat().st_mtime if target.is_file() else None,
        "display_name": display_name or user_profile(database_path)["display_name"],
    }


def user_profile(database_path: str | Path | None = None) -> dict[str, str]:
    initialize(database_path)
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT value FROM local_settings WHERE key = 'user_display_name'"
        ).fetchone()
    if row is None:
        return {"display_name": ""}
    try:
        value = json.loads(str(row["value"]))
    except json.JSONDecodeError:
        value = ""
    return {"display_name": str(value).strip()}


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
