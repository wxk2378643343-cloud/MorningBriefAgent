"""Deterministic Feishu lifestyle-message archiving for Obsidian."""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

from core.runtime import config
from core.runtime.locking import CrossProcessFileLock


_MEAL_RULES = (
    ("早餐", ("早餐", "早饭", "早上吃", "早上喝")),
    ("午餐", ("午餐", "午饭", "中午饭", "中饭", "中午吃")),
    ("晚餐", ("晚餐", "晚饭", "晚上吃", "夜宵")),
    ("加餐", ("加餐", "练前餐", "练后餐", "练前吃", "练后吃", "零食", "香蕉")),
)
_WORKOUT_RECORD_MARKERS = (
    "训练成果",
    "训练记录",
    "训练打卡",
    "健身打卡",
    "运动打卡",
    "跑步打卡",
    "跑完",
    "练完",
    "刚训练",
    "刚健身",
    "今日训练完成",
    "今天训练完成",
)
_QUERY_MARKERS = (
    "吗",
    "什么",
    "怎么",
    "如何",
    "多少",
    "计划",
    "要不要",
    "是不是",
    "？",
    "?",
)
_RECORD_MARKERS = ("这是", "今天", "刚刚", "吃了", "喝了", "记录", "归档", "打卡")


def classify_lifestyle_record(text: str, *, has_images: bool = False) -> str | None:
    """Return a conservative record category, avoiding plan/advice questions."""
    normalized = re.sub(r"\s+", "", text or "")
    if not normalized:
        return None
    for category, markers in _MEAL_RULES:
        if any(marker in normalized for marker in markers):
            if (
                not has_images
                and any(marker in normalized for marker in _QUERY_MARKERS)
                and not any(marker in normalized for marker in _RECORD_MARKERS)
            ):
                return None
            return category
    if any(marker in normalized for marker in _WORKOUT_RECORD_MARKERS):
        return "训练打卡"
    if (
        any(marker in normalized for marker in ("记录到健身", "记到健身", "归档到健身"))
        and not any(marker in normalized for marker in _QUERY_MARKERS)
    ):
        return "生活记录"
    return None


def resolve_archive_dir() -> Path | None:
    """Resolve the configured fitness archive, with an existing-vault fallback."""
    if config.FITNESS_ARCHIVE_DIR:
        return Path(config.FITNESS_ARCHIVE_DIR)
    if not config.VAULT_ROOT:
        return None

    vault = Path(config.VAULT_ROOT)
    preferred = vault / "09 - 健身管理" / "05 - 训练日常打卡与复盘"
    if preferred.is_dir():
        return preferred

    if vault.is_dir():
        for fitness_dir in sorted(vault.glob("*健身*")):
            if not fitness_dir.is_dir():
                continue
            matches = sorted(fitness_dir.glob("*训练日常打卡与复盘*"))
            if matches:
                return matches[0]
    return vault / "Fitness"


def _safe_component(value: str, fallback: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" ._")
    return safe[:48] or fallback


def _record_file(archive_dir: Path, day: str) -> Path:
    return archive_dir / f"{day}-训练课表推送与执行记录.md"


def _new_record(day: str) -> str:
    return (
        "---\n"
        f'title: "{day} 训练课表推送与执行记录"\n'
        f"date: {day}\n"
        "tags:\n"
        "  - fitness\n"
        "  - lifestyle-log\n"
        'status: "持续记录"\n'
        "---\n\n"
        f"# 🏋️ {day} 训练与饮食记录\n"
    )


def _copy_images(
    image_paths: Iterable[str],
    archive_dir: Path,
    now: dt.datetime,
    category: str,
    message_id: str,
) -> list[Path]:
    day_dir = archive_dir / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    suffix_id = _safe_component(message_id[-8:], "message")
    category_name = _safe_component(category, "记录")

    for index, raw_path in enumerate(image_paths, 1):
        source = Path(raw_path)
        if not source.is_file():
            continue
        extension = source.suffix.lower() if source.suffix else ".jpg"
        filename = (
            f"{now.strftime('%Y-%m-%d-%H%M%S')}-"
            f"{category_name}-{suffix_id}-{index}{extension}"
        )
        destination = day_dir / filename
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        copied.append(destination)
    return copied


def archive_lifestyle_message(
    text: str,
    message_id: str,
    image_paths: Iterable[str] = (),
    *,
    now: dt.datetime | None = None,
    category: str | None = None,
) -> dict[str, Any] | None:
    """Append one Feishu lifestyle record and copy its images into the vault."""
    image_paths = list(image_paths)
    category = category or classify_lifestyle_record(
        text, has_images=bool(image_paths)
    )
    archive_dir = resolve_archive_dir()
    if not category or archive_dir is None:
        return None

    now = now or dt.datetime.now()
    day = now.strftime("%Y-%m-%d")
    marker = f"<!-- feishu-message:{message_id} -->"
    note_path = _record_file(archive_dir, day)
    lock_path = (
        config.PROJECT_ROOT
        / "data"
        / "locks"
        / f"feishu-lifestyle-{day}.lock"
    )

    with CrossProcessFileLock(lock_path, timeout=30):
        archive_dir.mkdir(parents=True, exist_ok=True)
        existing = ""
        if note_path.is_file():
            existing = note_path.read_text(encoding="utf-8", errors="ignore")
            if marker in existing:
                return {
                    "category": category,
                    "note_path": str(note_path),
                    "image_paths": [],
                    "duplicate": True,
                }
        else:
            note_path.write_text(_new_record(day), encoding="utf-8")

        copied = _copy_images(
            image_paths, archive_dir, now, category, message_id
        )
        description = re.sub(r"\s+", " ", text).strip()
        lines = [
            "",
            marker,
            f"## {now.strftime('%H:%M')} · {category}",
            f"- **飞书原始记录**：{description}",
        ]
        if copied:
            lines.append("- **实拍附件**：")
            for image_path in copied:
                relative = image_path.relative_to(archive_dir).as_posix()
                lines.append(f"  - ![{category}]({relative})")
        lines.append(f"- **来源消息**：`{message_id}`")
        with note_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")

    return {
        "category": category,
        "note_path": str(note_path),
        "image_paths": [str(path) for path in copied],
        "duplicate": False,
    }


__all__ = [
    "archive_lifestyle_message",
    "classify_lifestyle_record",
    "resolve_archive_dir",
]
