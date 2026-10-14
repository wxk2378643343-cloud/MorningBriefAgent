"""Shared configuration and Markdown/date helpers for review documents."""

from __future__ import annotations

import datetime
import os
import re
from typing import Optional, Tuple

from core.runtime import config


DAILY_DIR = config.REVIEW_DAILY_DIR
WEEKLY_DIR = config.REVIEW_WEEKLY_DIR
MONTHLY_DIR = config.REVIEW_MONTHLY_DIR
TODO_ARCHIVE_DIR = config.TODO_ARCHIVE_DIR


def ensure_review_directories() -> None:
    for directory in (DAILY_DIR, WEEKLY_DIR, MONTHLY_DIR, TODO_ARCHIVE_DIR):
        if directory:
            os.makedirs(directory, exist_ok=True)


def replace_markdown_section(content: str, header: str, new_body: str) -> str:
    pattern = re.compile(
        rf"(^\s*{re.escape(header)}\s*$\n)(.*?)(?=^\s*---\s*$|^\s*##\s+|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    updated, count = pattern.subn(
        lambda match: f"{match.group(1)}{new_body.rstrip()}\n\n",
        content,
        count=1,
    )
    return updated if count else content


def parse_date(date_str: Optional[str] = None) -> datetime.date:
    if not date_str:
        return datetime.date.today()
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return datetime.date.today()


def get_week_info(dt: datetime.date) -> Tuple[str, str, str, str]:
    year, week, weekday = dt.isocalendar()
    monday = dt - datetime.timedelta(days=weekday - 1)
    sunday = monday + datetime.timedelta(days=6)
    week_code = f"{year}-W{week:02d}"
    folder = f"{week_code} ({monday:%m.%d} - {sunday:%m.%d})"
    return week_code, folder, monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
