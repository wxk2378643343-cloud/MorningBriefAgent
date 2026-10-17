"""Recoverable knowledge-file deletion and restoration workflows."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from storage.data_sources import (
    hash_file,
    resolve_source_path,
    scan_source,
    source_root,
)
from storage.sqlite import connect, initialize


RECOVERY_DIRECTORY = ".morningbrief-trash"
DELETABLE_SUFFIXES = {".md", ".markdown", ".txt"}


class FileRecoveryConflictError(RuntimeError):
    """Raised when an idempotency key or restore target conflicts."""


def delete_file_recoverably(
    source_id: str,
    relative_path: str,
    *,
    request_id: str | None = None,
    database_path: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    """Atomically move a text file to the local recovery area."""
    initialize(database_path)
    root = source_root(source_id, database_path=database_path)
    target = resolve_source_path(root, relative_path)
    normalized_path = target.relative_to(root).as_posix()
    if normalized_path == RECOVERY_DIRECTORY or normalized_path.startswith(
        f"{RECOVERY_DIRECTORY}/"
    ):
        raise ValueError("recovery_path_is_reserved")
    if target.suffix.lower() not in DELETABLE_SUFFIXES:
        raise ValueError("only_text_files_can_be_deleted")

    idempotency_key = (request_id or f"delete-{uuid4().hex}").strip()
    if not idempotency_key:
        raise ValueError("request_id_required")
    if len(idempotency_key) > 200:
        raise ValueError("request_id_too_long")
    existing = _operation_by_request(
        source_id, idempotency_key, database_path=database_path
    )
    if existing:
        if existing["relative_path"] != normalized_path:
            raise FileRecoveryConflictError("request_id_reused_for_different_path")
        return _reconcile_operation(existing, database_path=database_path)
    if not target.is_file():
        raise FileNotFoundError(relative_path)

    operation_id = f"recovery-{uuid4().hex}"
    recovery_relative = (
        Path(RECOVERY_DIRECTORY) / operation_id / Path(normalized_path)
    ).as_posix()
    recovery_target = resolve_source_path(root, recovery_relative)
    content_hash = hash_file(target)
    try:
        with connect(database_path) as connection:
            connection.execute(
                """
                INSERT INTO file_recovery_operations
                  (id, request_id, data_source_id, relative_path, recovery_path,
                   content_hash, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    operation_id,
                    idempotency_key,
                    source_id,
                    normalized_path,
                    recovery_relative,
                    content_hash,
                ),
            )
    except sqlite3.IntegrityError:
        existing = _operation_by_request(
            source_id, idempotency_key, database_path=database_path
        )
        if existing and existing["relative_path"] == normalized_path:
            return _reconcile_operation(existing, database_path=database_path)
        raise FileRecoveryConflictError("request_id_reused_for_different_path")

    recovery_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.replace(recovery_target)
        scan_source(source_id, database_path=database_path)
    except OSError as exc:
        _record_error(operation_id, str(exc), database_path=database_path)
        raise
    _set_status(operation_id, "deleted", database_path=database_path)
    return get_file_recovery(
        source_id, operation_id, database_path=database_path
    )


def restore_file(
    source_id: str,
    operation_id: str,
    *,
    database_path: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    """Restore one deleted file without overwriting an existing target."""
    operation = get_file_recovery(
        source_id, operation_id, database_path=database_path
    )
    operation = _reconcile_operation(operation, database_path=database_path)
    if operation["status"] == "restored":
        return operation
    if operation["status"] != "deleted":
        raise FileRecoveryConflictError(
            f"recovery_not_restorable:{operation['status']}"
        )

    root = source_root(source_id, database_path=database_path)
    target = resolve_source_path(root, str(operation["relative_path"]))
    recovery_target = resolve_source_path(root, str(operation["recovery_path"]))
    if target.exists():
        raise FileRecoveryConflictError("restore_target_exists")
    if not recovery_target.is_file():
        raise FileNotFoundError(str(operation["recovery_path"]))
    if hash_file(recovery_target) != operation["content_hash"]:
        raise FileRecoveryConflictError("recovery_content_changed")

    target.parent.mkdir(parents=True, exist_ok=True)
    _set_status(operation_id, "restoring", database_path=database_path)
    try:
        os.link(recovery_target, target)
        recovery_target.unlink()
        scan_source(source_id, database_path=database_path)
    except FileExistsError as exc:
        _set_status(operation_id, "deleted", database_path=database_path)
        raise FileRecoveryConflictError("restore_target_exists") from exc
    except OSError as exc:
        _record_error(operation_id, str(exc), database_path=database_path)
        raise
    _set_status(operation_id, "restored", database_path=database_path)
    return get_file_recovery(
        source_id, operation_id, database_path=database_path
    )


def list_file_recoveries(
    source_id: str,
    *,
    status: str | None = "deleted",
    database_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, object]]:
    """List persisted recovery operations, newest first."""
    initialize(database_path)
    query = "SELECT * FROM file_recovery_operations WHERE data_source_id = ?"
    params: list[object] = [source_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC, rowid DESC"
    with connect(database_path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_file_recovery(
    source_id: str,
    operation_id: str,
    *,
    database_path: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    initialize(database_path)
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT * FROM file_recovery_operations
            WHERE id = ? AND data_source_id = ?
            """,
            (operation_id, source_id),
        ).fetchone()
    if row is None:
        raise KeyError(f"Unknown recovery operation: {operation_id}")
    return dict(row)


def reconcile_pending_file_operations(
    *,
    database_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, object]]:
    """Resolve interrupted delete/restore moves and refresh their indexes."""
    initialize(database_path)
    with connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM file_recovery_operations
            WHERE status IN ('pending', 'restoring')
            ORDER BY created_at, id
            """
        ).fetchall()
    results = []
    for row in rows:
        operation = dict(row)
        try:
            operation = _reconcile_operation(
                operation, database_path=database_path
            )
        except (FileRecoveryConflictError, FileNotFoundError, OSError):
            operation = get_file_recovery(
                str(operation["data_source_id"]),
                str(operation["id"]),
                database_path=database_path,
            )
        results.append(operation)
    return results


def _operation_by_request(
    source_id: str,
    request_id: str,
    *,
    database_path: str | os.PathLike[str] | None,
) -> dict[str, object] | None:
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT * FROM file_recovery_operations
            WHERE data_source_id = ? AND request_id = ?
            """,
            (source_id, request_id),
        ).fetchone()
    return dict(row) if row else None


def _reconcile_operation(
    operation: dict[str, object],
    *,
    database_path: str | os.PathLike[str] | None,
) -> dict[str, object]:
    status = str(operation["status"])
    if status not in {"pending", "restoring"}:
        return operation
    source_id = str(operation["data_source_id"])
    root = source_root(source_id, database_path=database_path)
    target = resolve_source_path(root, str(operation["relative_path"]))
    recovery_target = resolve_source_path(root, str(operation["recovery_path"]))
    target_exists = target.is_file()
    recovery_exists = recovery_target.is_file()

    if target_exists and recovery_exists:
        if (
            status == "restoring"
            and hash_file(target) == operation["content_hash"]
            and hash_file(recovery_target) == operation["content_hash"]
        ):
            recovery_target.unlink()
            scan_source(source_id, database_path=database_path)
            _set_status(
                str(operation["id"]),
                "restored",
                database_path=database_path,
            )
            return get_file_recovery(
                source_id,
                str(operation["id"]),
                database_path=database_path,
            )
        _record_error(
            str(operation["id"]),
            "recovery_and_target_both_exist",
            database_path=database_path,
        )
        raise FileRecoveryConflictError("recovery_and_target_both_exist")
    if recovery_exists:
        resolved_status = "deleted"
    elif target_exists:
        resolved_status = "restored" if status == "restoring" else "failed"
    else:
        _record_error(
            str(operation["id"]),
            "recovery_and_target_missing",
            database_path=database_path,
        )
        raise FileNotFoundError(str(operation["relative_path"]))

    scan_source(source_id, database_path=database_path)
    _set_status(
        str(operation["id"]), resolved_status, database_path=database_path
    )
    if resolved_status == "failed":
        _record_error(
            str(operation["id"]),
            "delete_not_started",
            database_path=database_path,
        )
    return get_file_recovery(
        source_id, str(operation["id"]), database_path=database_path
    )


def _set_status(
    operation_id: str,
    status: str,
    *,
    database_path: str | os.PathLike[str] | None,
) -> None:
    deleted_at = "CURRENT_TIMESTAMP" if status == "deleted" else "deleted_at"
    restored_at = "CURRENT_TIMESTAMP" if status == "restored" else "restored_at"
    with connect(database_path) as connection:
        connection.execute(
            f"""
            UPDATE file_recovery_operations
            SET status = ?, error_message = NULL,
                deleted_at = {deleted_at}, restored_at = {restored_at},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, operation_id),
        )


def _record_error(
    operation_id: str,
    message: str,
    *,
    database_path: str | os.PathLike[str] | None,
) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """
            UPDATE file_recovery_operations
            SET error_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (message[:1000], operation_id),
        )
