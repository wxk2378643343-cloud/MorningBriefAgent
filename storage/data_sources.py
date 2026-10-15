"""Repositories for user-configured local data sources and indexed files."""

from __future__ import annotations

import hashlib
import base64
import mimetypes
import os
import sqlite3
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from storage.sqlite import connect, initialize


def register_source(
    name: str,
    root_path: str | os.PathLike[str],
    *,
    source_type: str = "local_folder",
    read_only: bool = True,
    source_id: str | None = None,
    database_path: str | os.PathLike[str] | None = None,
) -> str:
    """Register a local directory without copying or moving its contents."""
    root = Path(root_path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    initialize(database_path)
    identifier = source_id or f"source-{uuid4().hex}"
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO data_sources
              (id, name, source_type, root_path, read_only, enabled)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(root_path) DO UPDATE SET
              name=excluded.name,
              source_type=excluded.source_type,
              read_only=excluded.read_only,
              enabled=1,
              updated_at=CURRENT_TIMESTAMP
            """,
            (identifier, name.strip() or root.name, source_type, str(root), int(read_only)),
        )
        row = connection.execute(
            "SELECT id FROM data_sources WHERE root_path = ?", (str(root),)
        ).fetchone()
    return str(row["id"])


def list_sources(
    *,
    enabled_only: bool = True,
    database_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, object]]:
    initialize(database_path)
    clause = "WHERE enabled = 1" if enabled_only else ""
    with connect(database_path) as connection:
        rows = connection.execute(
            f"SELECT * FROM data_sources {clause} ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]


def _file_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".md": "markdown",
        ".json": "json",
        ".sqlite": "sqlite",
        ".sqlite3": "sqlite",
        ".log": "log",
        ".jpg": "image",
        ".jpeg": "image",
        ".png": "image",
        ".gif": "image",
        ".pdf": "pdf",
    }.get(suffix, "file")


def _hash_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def scan_source(
    source_id: str,
    *,
    include_hidden: bool = False,
    database_path: str | os.PathLike[str] | None = None,
) -> int:
    """Index file metadata for one source; original files remain untouched."""
    initialize(database_path)
    with connect(database_path) as connection:
        source = connection.execute(
            "SELECT root_path FROM data_sources WHERE id = ? AND enabled = 1",
            (source_id,),
        ).fetchone()
        if source is None:
            raise KeyError(f"Unknown data source: {source_id}")
        root = Path(str(source["root_path"]))
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        seen: set[str] = set()
        indexed = 0
        for path in _iter_files(root, include_hidden=include_hidden):
            relative = path.relative_to(root).as_posix()
            seen.add(relative)
            stat = path.stat()
            connection.execute(
                """
                INSERT INTO file_records
                  (id, data_source_id, relative_path, file_name, file_type,
                   size_bytes, modified_at, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(data_source_id, relative_path) DO UPDATE SET
                  file_name=excluded.file_name,
                  file_type=excluded.file_type,
                  size_bytes=excluded.size_bytes,
                  modified_at=excluded.modified_at,
                  content_hash=excluded.content_hash,
                  indexed_at=CURRENT_TIMESTAMP
                """,
                (
                    f"file-{uuid4().hex}",
                    source_id,
                    relative,
                    path.name,
                    _file_type(path),
                    stat.st_size,
                    str(stat.st_mtime),
                    _hash_file(path),
                ),
            )
            indexed += 1
        if seen:
            placeholders = ",".join("?" for _ in seen)
            connection.execute(
                f"""
                DELETE FROM file_records
                WHERE data_source_id = ? AND relative_path NOT IN ({placeholders})
                """,
                (source_id, *seen),
            )
        else:
            connection.execute(
                "DELETE FROM file_records WHERE data_source_id = ?", (source_id,)
            )
    return indexed


def list_files(
    source_id: str,
    *,
    file_type: str | None = None,
    database_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, object]]:
    initialize(database_path)
    query = "SELECT * FROM file_records WHERE data_source_id = ?"
    params: list[object] = [source_id]
    if file_type:
        query += " AND file_type = ?"
        params.append(file_type)
    query += " ORDER BY relative_path"
    with connect(database_path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def read_file_preview(
    source_id: str,
    relative_path: str,
    *,
    max_bytes: int = 128 * 1024,
    database_path: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    """Read a bounded text preview from a registered source."""
    initialize(database_path)
    with connect(database_path) as connection:
        source = connection.execute(
            "SELECT root_path FROM data_sources WHERE id = ? AND enabled = 1",
            (source_id,),
        ).fetchone()
    if source is None:
        raise KeyError(f"Unknown data source: {source_id}")
    root = Path(str(source["root_path"])).resolve()
    target = (root / relative_path).resolve()
    if root != target and root not in target.parents:
        raise ValueError("Path escapes data source root")
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    if target.stat().st_size > max_bytes:
        raise ValueError("file_too_large_for_preview")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("binary_file_not_supported") from exc
    return {
        "relative_path": target.relative_to(root).as_posix(),
        "file_name": target.name,
        "file_type": _file_type(target),
        "content": content,
        "size_bytes": target.stat().st_size,
    }


def read_file_binary(
    source_id: str,
    relative_path: str,
    *,
    max_bytes: int = 5 * 1024 * 1024,
    database_path: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    """Read a bounded binary file as base64 for local image/PDF preview."""
    initialize(database_path)
    with connect(database_path) as connection:
        source = connection.execute(
            "SELECT root_path FROM data_sources WHERE id = ? AND enabled = 1",
            (source_id,),
        ).fetchone()
    if source is None:
        raise KeyError(f"Unknown data source: {source_id}")
    root = Path(str(source["root_path"])).resolve()
    target = (root / relative_path).resolve()
    if root != target and root not in target.parents:
        raise ValueError("Path escapes data source root")
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    if target.stat().st_size > max_bytes:
        raise ValueError("file_too_large_for_preview")
    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if content_type not in {"application/pdf", "image/jpeg", "image/png", "image/gif"}:
        raise ValueError("binary_preview_not_supported")
    return {
        "relative_path": target.relative_to(root).as_posix(),
        "file_name": target.name,
        "file_type": _file_type(target),
        "content_type": content_type,
        "content_base64": base64.b64encode(target.read_bytes()).decode("ascii"),
        "size_bytes": target.stat().st_size,
    }


def inspect_sqlite(
    source_id: str,
    relative_path: str,
    *,
    table: str | None = None,
    limit: int = 50,
    database_path: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    """Read SQLite schema or a bounded page of rows without mutating it."""
    initialize(database_path)
    with connect(database_path) as connection:
        source = connection.execute(
            "SELECT root_path FROM data_sources WHERE id = ? AND enabled = 1",
            (source_id,),
        ).fetchone()
    if source is None:
        raise KeyError(f"Unknown data source: {source_id}")
    root = Path(str(source["root_path"])).resolve()
    target = (root / relative_path).resolve()
    if root != target and root not in target.parents:
        raise ValueError("Path escapes data source root")
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    if target.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}:
        raise ValueError("not_sqlite_file")
    bounded_limit = max(1, min(int(limit), 100))
    uri = f"file:{target.as_posix()}?mode=ro"
    database = sqlite3.connect(uri, uri=True)
    try:
        database.row_factory = sqlite3.Row
        tables = [
            str(row["name"])
            for row in database.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        result: dict[str, object] = {
            "file_name": target.name,
            "tables": tables,
        }
        if table is not None:
            if table not in tables:
                raise KeyError(f"Unknown table: {table}")
            quoted_table = '"' + table.replace('"', '""') + '"'
            rows = database.execute(
                f"SELECT * FROM {quoted_table} LIMIT ?", (bounded_limit,)
            ).fetchall()
            result["columns"] = [item[0] for item in database.execute(
                f"SELECT * FROM {quoted_table} LIMIT 0"
            ).description or []]
            result["rows"] = [dict(row) for row in rows]
            result["limit"] = bounded_limit
    finally:
        database.close()
    return result


def _iter_files(root: Path, *, include_hidden: bool) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not include_hidden and any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        yield path
