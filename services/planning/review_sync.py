"""Compatibility facade for daily, weekly, and monthly review workflows."""

from __future__ import annotations

from typing import Dict, List, Optional

from core.runtime import config

from . import review_common, review_daily, review_monthly, review_weekly


VAULT_ROOT = config.VAULT_ROOT
DAILY_DIR = config.REVIEW_DAILY_DIR
WEEKLY_DIR = config.REVIEW_WEEKLY_DIR
MONTHLY_DIR = config.REVIEW_MONTHLY_DIR
TODO_ARCHIVE_DIR = config.TODO_ARCHIVE_DIR


def _sync_review_paths() -> None:
    """Keep legacy module-level path overrides working for callers/tests."""
    review_common.DAILY_DIR = DAILY_DIR
    review_common.WEEKLY_DIR = WEEKLY_DIR
    review_common.MONTHLY_DIR = MONTHLY_DIR
    review_common.TODO_ARCHIVE_DIR = TODO_ARCHIVE_DIR


def ensure_review_directories() -> None:
    _sync_review_paths()
    review_common.ensure_review_directories()


replace_markdown_section = review_common.replace_markdown_section
parse_date = review_common.parse_date
get_week_info = review_common.get_week_info


def ensure_daily_journal(date_str: str, todos: List[str]) -> str:
    _sync_review_paths()
    return review_daily.ensure_daily_journal(date_str, todos)


def sync_todo_completion_to_journal(
    completed_names: List[str],
    date_str: Optional[str] = None,
) -> bool:
    _sync_review_paths()
    return review_daily.sync_todo_completion_to_journal(completed_names, date_str)


def ensure_weekly_report(date_str: str) -> str:
    _sync_review_paths()
    return review_weekly.ensure_weekly_report(date_str)


def update_weekly_todo_matrix(
    date_str: str,
    total_count: int,
    completed_count: int,
) -> bool:
    _sync_review_paths()
    return review_weekly.update_weekly_todo_matrix(
        date_str, total_count, completed_count
    )


def ensure_monthly_report(date_str: str) -> str:
    _sync_review_paths()
    return review_monthly.ensure_monthly_report(date_str)


def cascade_sync_all(date_str: str, todos: List[str]) -> Dict[str, str]:
    """Run daily, weekly, and monthly synchronization in dependency order."""
    return {
        "daily": ensure_daily_journal(date_str, todos),
        "weekly": ensure_weekly_report(date_str),
        "monthly": ensure_monthly_report(date_str),
    }
