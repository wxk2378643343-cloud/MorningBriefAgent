"""Allowlisted, parameterized database browser for the local UI."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from storage.sqlite import connect

TABLES = {
    "todo_records": "id", "schedule_records": "id", "fund_records": "id",
    "fund_market_snapshots": "id", "news_items": "id",
    "meal_records": "fact_id", "workout_records": "fact_id",
}


def tables(database_path: str | Path) -> list[dict[str, Any]]:
    with connect(database_path) as db:
        result = []
        for name, key in TABLES.items():
            columns = [dict(row) for row in db.execute(f"PRAGMA table_info({name})")]
            count = db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            result.append({"name": name, "primary_key": key, "columns": columns, "count": count})
        return result


def rows(database_path: str | Path, table: str, limit: int = 50) -> dict[str, Any]:
    _check(table)
    with connect(database_path) as db:
        columns = [dict(row) for row in db.execute(f"PRAGMA table_info({table})")]
        values = [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (min(limit, 100),))]
        return {"table": table, "primary_key": TABLES[table], "columns": columns, "rows": values}


def create(database_path: str | Path, table: str, record: dict[str, Any]) -> dict:
    _check(table)
    return _write(database_path, table, record, None)


def update(database_path: str | Path, table: str, key: Any, record: dict[str, Any]) -> dict:
    _check(table)
    return _write(database_path, table, record, key)


def delete(database_path: str | Path, table: str, key: Any) -> None:
    _check(table)
    with connect(database_path) as db:
        db.execute(f"DELETE FROM {table} WHERE {TABLES[table]} = ?", (key,))


def _check(table: str) -> None:
    if table not in TABLES:
        raise ValueError("table_not_allowed")


def _write(database_path: str | Path, table: str, record: dict[str, Any], key: Any) -> dict:
    if not isinstance(record, dict) or not record:
        raise ValueError("record_required")
    with connect(database_path) as db:
        allowed = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        clean = {name: value for name, value in record.items() if name in allowed}
        if not clean:
            raise ValueError("no_valid_columns")
        if key is None:
            names = list(clean)
            db.execute(
                f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})",
                [clean[name] for name in names],
            )
            key = clean.get(TABLES[table], db.execute("SELECT last_insert_rowid()").fetchone()[0])
        else:
            assignments = ", ".join(f"{name}=?" for name in clean if name != TABLES[table])
            if assignments:
                db.execute(
                    f"UPDATE {table} SET {assignments} WHERE {TABLES[table]}=?",
                    [clean[name] for name in clean if name != TABLES[table]] + [key],
                )
        row = db.execute(
            f"SELECT * FROM {table} WHERE {TABLES[table]} = ?", (key,)
        ).fetchone()
    return dict(row) if row is not None else {}
