"""Repositories for user-configured local data sources and indexed files."""

from __future__ import annotations

import hashlib
import base64
import mimetypes
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from typing import Iterable
from uuid import uuid4

from storage.sqlite import connect, initialize


@dataclass(frozen=True)
class FileMoveResult:
    """Result of moving a file within one registered data source."""

    source_path: str
    destination_path: str


class FileMoveError(ValueError):
    """Stable storage error that never includes an absolute local path."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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
    sort: str = "path",
    limit: int | None = None,
    database_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, object]]:
    """Return the stable file metadata contract for one registered source."""
    initialize(database_path)
    if sort not in {"path", "recent"}:
        raise ValueError(f"unsupported_file_sort:{sort}")
    if limit is not None and not 1 <= limit <= 5000:
        raise ValueError("file_limit_out_of_range")
    query = """
        SELECT files.*, sources.name AS source_name,
               sources.source_type AS source_type,
               sources.root_path AS source_root
        FROM file_records AS files
        JOIN data_sources AS sources ON sources.id = files.data_source_id
        WHERE files.data_source_id = ?
    """
    params: list[object] = [source_id]
    if file_type:
        query += " AND files.file_type = ?"
        params.append(file_type)
    if sort == "recent":
        query += """
            ORDER BY
              CASE
                WHEN files.modified_at IS NULL
                  OR TRIM(files.modified_at) = ''
                  OR CAST(files.modified_at AS REAL) <= 0
                THEN 1 ELSE 0
              END,
              CAST(files.modified_at AS REAL) DESC,
              files.relative_path COLLATE NOCASE ASC,
              files.id ASC
        """
    else:
        query += (
            " ORDER BY files.relative_path COLLATE NOCASE ASC, files.id ASC"
        )
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with connect(database_path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [_file_metadata_contract(dict(row)) for row in rows]


def _file_metadata_contract(row: dict[str, object]) -> dict[str, object]:
    """Project persisted index data and current file metadata for API consumers."""
    source_root = Path(str(row.pop("source_root", ""))).resolve()
    source = {
        "id": str(row["data_source_id"]),
        "name": str(row.pop("source_name", "") or ""),
        "type": str(row.pop("source_type", "") or "unknown"),
    }
    row["source"] = source
    row["updated_at"] = _timestamp_as_utc(row.get("modified_at"))
    row["sync_status"] = _file_sync_status(row, source_root)
    return row


def _timestamp_as_utc(value: object) -> str | None:
    try:
        timestamp = float(str(value))
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    try:
        return (
            datetime.fromtimestamp(timestamp, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
    except (OSError, OverflowError, ValueError):
        return None


def _file_sync_status(row: dict[str, object], source_root: Path) -> str:
    """Compare the durable index snapshot with current local file metadata."""
    relative_path = str(row.get("relative_path") or "")
    target = (source_root / relative_path).resolve()
    if source_root != target and source_root not in target.parents:
        return "unknown"
    try:
        stat = target.stat()
    except (FileNotFoundError, OSError):
        return "missing"
    try:
        indexed_size = int(row["size_bytes"])
        indexed_modified = float(str(row["modified_at"]))
    except (KeyError, TypeError, ValueError):
        return "unknown"
    if not row.get("content_hash") or indexed_modified <= 0:
        return "unknown"
    if indexed_size != stat.st_size or abs(indexed_modified - stat.st_mtime) > 0.000001:
        return "stale"
    return "synced"


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


def write_file_text(
    source_id: str,
    relative_path: str,
    content: str,
    *,
    database_path: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    """Write a Markdown/text file inside a registered source and return its metadata."""
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
    if root == target or root not in target.parents:
        raise ValueError("Path escapes data source root")
    if target.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("only_text_files_can_be_written")
    if len(content.encode("utf-8")) > 512 * 1024:
        raise ValueError("file_too_large")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    scan_source(source_id, database_path=database_path)
    return read_file_preview(source_id, relative_path, database_path=database_path)


def delete_file(
    source_id: str,
    relative_path: str,
    *,
    database_path: str | os.PathLike[str] | None = None,
) -> None:
    """Delete a text file inside a registered source."""
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
    if root == target or root not in target.parents:
        raise ValueError("Path escapes data source root")
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    if target.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("only_text_files_can_be_deleted")
    target.unlink()
    scan_source(source_id, database_path=database_path)


def move_file(
    source_id: str,
    relative_path: str,
    destination_path: str,
    *,
    database_path: str | os.PathLike[str] | None = None,
) -> FileMoveResult:
    """Move one file safely inside a source, without replacing another file."""
    root = _enabled_source_root(source_id, database_path=database_path)
    source = _safe_source_target(root, relative_path)
    destination = _safe_source_target(root, destination_path)
    if source == destination:
        raise FileMoveError("destination_same_as_source")
    if not source.is_file():
        raise FileMoveError("file_not_found")
    if destination.exists():
        raise FileMoveError("destination_exists")
    if destination.parent.exists() and not destination.parent.is_dir():
        raise FileMoveError("destination_parent_invalid")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        _move_without_overwrite(source, destination)
    except FileExistsError as exc:
        raise FileMoveError("destination_exists") from exc
    except OSError as exc:
        raise FileMoveError("file_move_failed") from exc

    try:
        scan_source(source_id, database_path=database_path)
    except Exception as exc:
        try:
            if destination.is_file() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                _move_without_overwrite(destination, source)
            scan_source(source_id, database_path=database_path)
        except Exception:
            pass
        raise FileMoveError("file_index_update_failed") from exc

    return FileMoveResult(
        source_path=_relative_posix_path(root, source),
        destination_path=_relative_posix_path(root, destination),
    )


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


def _enabled_source_root(
    source_id: str,
    *,
    database_path: str | os.PathLike[str] | None = None,
) -> Path:
    initialize(database_path)
    with connect(database_path) as connection:
        source = connection.execute(
            "SELECT root_path FROM data_sources WHERE id = ? AND enabled = 1",
            (source_id,),
        ).fetchone()
    if source is None:
        raise FileMoveError("data_source_not_found")
    root = Path(str(source["root_path"])).resolve()
    if not root.is_dir():
        raise FileMoveError("data_source_unavailable")
    return root


def _safe_source_target(root: Path, relative_path: str) -> Path:
    candidate = str(relative_path).strip()
    windows_path = PureWindowsPath(candidate)
    normalized = candidate.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    if (
        not candidate
        or "\x00" in candidate
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or posix_path.is_absolute()
        or any(part in {"", ".", ".."} for part in posix_path.parts)
    ):
        raise FileMoveError("invalid_relative_path")
    target = (root / Path(*posix_path.parts)).resolve()
    if root == target or root not in target.parents:
        raise FileMoveError("invalid_relative_path")
    return target


def _relative_posix_path(root: Path, target: Path) -> str:
    return target.relative_to(root).as_posix()


def _move_without_overwrite(source: Path, destination: Path) -> None:
    """Move a regular file with no-replace semantics on Windows and POSIX."""
    if os.name == "nt":
        source.rename(destination)
        return
    os.link(source, destination)
    try:
        source.unlink()
    except OSError:
        destination.unlink(missing_ok=True)
        raise
