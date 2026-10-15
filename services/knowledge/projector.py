"""Deterministic Markdown projections for the configured Obsidian vault."""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any

from core.runtime import config
from storage.sqlite import connect, initialize


def _target(vault_root: str | None, env_name: str, relative: str) -> Path:
    configured = getattr(config, env_name, "")
    if configured:
        return Path(configured)
    return Path(vault_root or config.OBSIDIAN_VAULT_ROOT) / relative


def _write_projection(path: Path, title: str, body: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "---\n"
        "generated_by: MorningBriefAgent\n"
        f"updated_at: {dt.datetime.now().isoformat(timespec='seconds')}\n"
        "---\n\n"
        f"# {title}\n\n{body.rstrip()}\n"
    )
    path.write_text(content, encoding="utf-8")
    return str(path)


def _record_projection(
    *,
    projection_key: str,
    target_path: str,
    source_id: str,
    content: str,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    initialize()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO projection_records
            (projection_key, target_path, source_type, source_id, content_hash,
             status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(projection_key, source_id) DO UPDATE SET
              target_path=excluded.target_path,
              content_hash=excluded.content_hash,
              status=excluded.status,
              error_message=excluded.error_message,
              projected_at=CURRENT_TIMESTAMP
            """,
            (
                projection_key,
                target_path,
                "plan",
                source_id,
                hashlib.sha256(content.encode("utf-8")).hexdigest(),
                status,
                error_message,
            ),
        )


def project_plan(
    plan: dict[str, Any],
    *,
    vault_root: str | None = None,
) -> list[str]:
    """Project a plan into dedicated Markdown files without touching user notes."""
    target_date = str(plan.get("date", "")).strip() or dt.date.today().isoformat()
    todo_lines = []
    for title in plan.get("todos", []):
        title = str(title).strip()
        if title:
            todo_lines.append(f"- [ ] {title}")

    schedule_lines = []
    for slot in plan.get("schedule_slots", []):
        if not isinstance(slot, dict):
            continue
        name = str(slot.get("name", "")).strip()
        start = str(slot.get("start", "")).strip()
        end = str(slot.get("end", "")).strip()
        if name and start and end:
            schedule_lines.append(f"- {start}–{end} {name}")

    projections = [
        ("todo", _target(vault_root, "TODO_MARKDOWN_PATH", "03 - 待办事项/Agent-今日待办.md"),
         f"{target_date} Agent 待办", "\n".join(todo_lines) or "暂无待办。"),
        ("schedule", _target(vault_root, "SCHEDULE_MARKDOWN_PATH", "03 - 待办事项/Agent-日程.md"),
         f"{target_date} Agent 日程", "\n".join(schedule_lines) or "暂无日程。"),
    ]
    paths = []
    for key, path, title, body in projections:
        content = (
            "---\n"
            "generated_by: MorningBriefAgent\n"
            f"updated_at: {dt.datetime.now().isoformat(timespec='seconds')}\n"
            "---\n\n"
            f"# {title}\n\n{body.rstrip()}\n"
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            _record_projection(
                projection_key=key, target_path=str(path),
                source_id=f"plan:{target_date}", content=content,
            )
            paths.append(str(path))
        except OSError as exc:
            _record_projection(
                projection_key=key, target_path=str(path),
                source_id=f"plan:{target_date}", content=content,
                status="failed", error_message=str(exc),
            )
            raise
    return paths
