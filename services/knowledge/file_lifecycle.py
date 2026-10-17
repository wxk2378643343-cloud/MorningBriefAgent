"""Application service for safe knowledge-base file lifecycle operations."""

from __future__ import annotations

import os
from dataclasses import dataclass

from storage.data_sources import FileMoveError, move_file


MARKDOWN_SUFFIXES = {".md", ".markdown"}


@dataclass(frozen=True)
class FileLifecycleCommand:
    source_id: str
    path: str
    destination_path: str
    destination_source_id: str | None = None


class FileLifecycleError(ValueError):
    """Stable application error suitable for a local API response."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def relocate_markdown_file(
    command: FileLifecycleCommand,
    *,
    database_path: str | os.PathLike[str] | None = None,
) -> dict[str, object]:
    """Rename or move a Markdown file within its current data source."""
    source_id = command.source_id.strip()
    destination_source_id = (command.destination_source_id or source_id).strip()
    if not source_id:
        raise FileLifecycleError("source_id_required")
    if destination_source_id != source_id:
        raise FileLifecycleError("cross_source_move_not_allowed")
    if not _is_markdown_path(command.path) or not _is_markdown_path(
        command.destination_path
    ):
        raise FileLifecycleError("only_markdown_files_can_be_moved")

    try:
        result = move_file(
            source_id,
            command.path,
            command.destination_path,
            database_path=database_path,
        )
    except FileMoveError as exc:
        raise FileLifecycleError(exc.code) from exc
    except OSError as exc:
        raise FileLifecycleError("file_move_failed") from exc

    return {
        "source_path": result.source_path,
        "destination_path": result.destination_path,
    }


def _is_markdown_path(value: str) -> bool:
    normalized = str(value).replace("\\", "/").rstrip("/")
    if not normalized:
        return False
    suffix = os.path.splitext(normalized)[1].lower()
    return suffix in MARKDOWN_SUFFIXES
