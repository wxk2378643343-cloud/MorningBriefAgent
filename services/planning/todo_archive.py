"""Todo plan archive helpers."""

from __future__ import annotations

import datetime
import os


def get_weekly_archive_dir(archive_base: str, date_str: str) -> str:
    """Return and create the ISO-week directory for a plan date."""
    try:
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        target_date = datetime.date.today()
    year, week, weekday = target_date.isocalendar()
    monday = target_date - datetime.timedelta(days=weekday - 1)
    sunday = monday + datetime.timedelta(days=6)
    folder = f"{year}-W{week:02d} ({monday:%m.%d} - {sunday:%m.%d})"
    target_dir = os.path.join(archive_base, folder)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


def archive_plan(archive_base: str, date_str: str, content: str) -> str:
    """Archive one plan document and return its path."""
    directory = get_weekly_archive_dir(archive_base, date_str)
    target = os.path.join(directory, f"{date_str} plan.md")
    with open(target, "w", encoding="utf-8") as file:
        file.write(content)
    return target
