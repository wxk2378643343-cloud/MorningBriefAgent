"""Safe, editor-agnostic synchronization between local knowledge folders."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol


IGNORED_DIRECTORIES = {".git", ".morningbrief-trash"}


class KnowledgeStore(Protocol):
    """Minimal storage boundary used by knowledge workflows."""

    @property
    def root(self) -> Path: ...

    def files(self) -> dict[str, str]: ...

    def copy_from(self, source: "KnowledgeStore", relative_path: str) -> None: ...


@dataclass(frozen=True)
class FolderSyncCommand:
    source_root: str | os.PathLike[str]
    target_root: str | os.PathLike[str]
    apply: bool = False


class FolderSyncError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class LocalFolderStore:
    """KnowledgeStore backed by a normal local folder."""

    def __init__(self, root: str | os.PathLike[str]):
        self._root = Path(root).expanduser().resolve()
        if not self._root.is_dir():
            raise FolderSyncError("folder_not_found")

    @property
    def root(self) -> Path:
        return self._root

    def files(self) -> dict[str, str]:
        return {
            path.relative_to(self.root).as_posix(): _hash_file(path)
            for path in _iter_files(self.root)
        }

    def copy_from(self, source: KnowledgeStore, relative_path: str) -> None:
        source_path = _safe_child(source.root, relative_path)
        target_path = _safe_child(self.root, relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target_path.name}.",
            suffix=".sync",
            dir=target_path.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copy2(source_path, temporary)
            try:
                os.link(temporary, target_path)
            except FileExistsError as exc:
                raise FolderSyncError("target_changed_during_sync") from exc
        finally:
            temporary.unlink(missing_ok=True)


def synchronize_folders(command: FolderSyncCommand) -> dict[str, object]:
    """Copy missing files without deleting or overwriting target content."""
    source = LocalFolderStore(command.source_root)
    target = LocalFolderStore(command.target_root)
    if source.root == target.root:
        raise FolderSyncError("source_and_target_are_same")
    if source.root in target.root.parents or target.root in source.root.parents:
        raise FolderSyncError("nested_folders_not_allowed")

    source_files = source.files()
    target_files = target.files()
    added = sorted(set(source_files) - set(target_files))
    unchanged = sorted(
        path
        for path in set(source_files) & set(target_files)
        if source_files[path] == target_files[path]
    )
    conflicts = sorted(
        path
        for path in set(source_files) & set(target_files)
        if source_files[path] != target_files[path]
    )

    copied: list[str] = []
    if command.apply:
        for relative_path in added:
            try:
                target.copy_from(source, relative_path)
                copied.append(relative_path)
            except FolderSyncError as exc:
                if exc.code != "target_changed_during_sync":
                    raise
                conflicts.append(relative_path)

    return {
        "applied": command.apply,
        "source_file_count": len(source_files),
        "target_file_count": len(target_files),
        "added": added,
        "copied": copied,
        "unchanged": unchanged,
        "conflicts": sorted(conflicts),
        "deleted": [],
    }


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") or part in IGNORED_DIRECTORIES for part in relative.parts):
            continue
        yield path


def _safe_child(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    if root == target or root not in target.parents:
        raise FolderSyncError("invalid_relative_path")
    return target


def _hash_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
