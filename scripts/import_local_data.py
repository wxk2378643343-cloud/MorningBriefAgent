"""Import existing local JSON/Markdown data into the structured SQLite store."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.runtime import config
from services.finance.fund_advisor import load_portfolio_config
from services.planning.plan_generation import load_staged_plan
from storage.market import save_fund_position
from storage.planning import persist_plan
from storage.sqlite import connect, initialize


def import_markdown_sources(vault_root: str | None, database: str) -> int:
    """Index Markdown files without guessing their semantic facts."""
    if not vault_root:
        return 0
    root = Path(vault_root)
    if not root.is_dir():
        return 0
    count = 0
    initialize(database)
    with connect(database) as connection:
        for path in root.rglob("*.md"):
            source_id = "obsidian:" + hashlib.sha256(
                str(path.resolve()).encode("utf-8")
            ).hexdigest()[:24]
            connection.execute(
                """
                INSERT OR IGNORE INTO source_records
                  (id, source_type, source_path, recorded_at)
                VALUES (?, 'obsidian_markdown', ?, CURRENT_TIMESTAMP)
                """,
                (source_id, str(path.resolve())),
            )
            count += 1
    return count


def import_local_data(database: str) -> dict[str, int]:
    initialize(database)
    portfolio_data = load_portfolio_config()
    recorded_at = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(timespec="seconds")
    portfolio_count = 0
    source_id = f"portfolio:{config.PORTFOLIO_FILE}"
    for item in portfolio_data.get("portfolio", []):
        code = str(item.get("code", "")).strip()
        if not code:
            continue
        save_fund_position(
            fund_code=code,
            fund_name=str(item.get("name", "")),
            shares=float(item["shares"]) if item.get("shares") is not None else None,
            cost_price=(
                float(item["cost_price"])
                if item.get("cost_price") is not None else None
            ),
            source_id=source_id,
            recorded_at=recorded_at,
            database_path=database,
        )
        portfolio_count += 1

    plan = load_staged_plan()
    if plan:
        persist_plan(plan, database_path=database)
    todo_count = len(plan.get("todos", [])) if plan else 0
    schedule_count = len(plan.get("schedule_slots", [])) if plan else 0
    markdown_count = import_markdown_sources(
        getattr(config, "OBSIDIAN_VAULT_ROOT", ""),
        database,
    )
    return {
        "portfolio": portfolio_count,
        "todos": todo_count,
        "schedules": schedule_count,
        "markdown_sources": markdown_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import local data into SQLite")
    parser.add_argument(
        "--database",
        default=str(config.SQLITE_DATABASE_PATH),
        help="SQLite database path",
    )
    args = parser.parse_args()
    result = import_local_data(args.database)
    print("本地数据导入完成：")
    for key, value in result.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
