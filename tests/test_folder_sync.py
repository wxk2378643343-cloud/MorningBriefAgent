import tempfile
import unittest
from pathlib import Path

from services.knowledge.folder_sync import (
    FolderSyncCommand,
    FolderSyncError,
    LocalFolderStore,
    synchronize_folders,
)


class FolderSyncTests(unittest.TestCase):
    def test_preview_and_apply_copy_only_missing_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.mkdir()
            target.mkdir()
            (source / "notes").mkdir()
            (source / "notes" / "new.md").write_text("new", encoding="utf-8")
            (source / "same.md").write_text("same", encoding="utf-8")
            (target / "same.md").write_text("same", encoding="utf-8")

            preview = synchronize_folders(FolderSyncCommand(source, target))
            self.assertFalse(preview["applied"])
            self.assertEqual(["notes/new.md"], preview["added"])
            self.assertFalse((target / "notes" / "new.md").exists())

            applied = synchronize_folders(
                FolderSyncCommand(source, target, apply=True)
            )
            self.assertEqual(["notes/new.md"], applied["copied"])
            self.assertEqual(
                "new",
                (target / "notes" / "new.md").read_text(encoding="utf-8"),
            )

    def test_conflicts_never_overwrite_or_delete_target_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.mkdir()
            target.mkdir()
            (source / "note.md").write_text("source", encoding="utf-8")
            (target / "note.md").write_text("target", encoding="utf-8")
            (target / "target-only.md").write_text("keep", encoding="utf-8")

            result = synchronize_folders(
                FolderSyncCommand(source, target, apply=True)
            )

            self.assertEqual(["note.md"], result["conflicts"])
            self.assertEqual("target", (target / "note.md").read_text(encoding="utf-8"))
            self.assertEqual(
                "keep",
                (target / "target-only.md").read_text(encoding="utf-8"),
            )
            self.assertEqual([], result["deleted"])

    def test_rejects_same_nested_and_symlinked_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source.mkdir()
            nested = source / "nested"
            nested.mkdir()
            with self.assertRaisesRegex(
                FolderSyncError, "source_and_target_are_same"
            ):
                synchronize_folders(FolderSyncCommand(source, source))
            with self.assertRaisesRegex(FolderSyncError, "nested_folders"):
                synchronize_folders(FolderSyncCommand(source, nested))

    def test_store_ignores_hidden_runtime_and_symlink_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "root"
            root.mkdir()
            (root / "visible.md").write_text("visible", encoding="utf-8")
            (root / ".hidden.md").write_text("hidden", encoding="utf-8")
            trash = root / ".morningbrief-trash"
            trash.mkdir()
            (trash / "deleted.md").write_text("deleted", encoding="utf-8")
            self.assertEqual(["visible.md"], sorted(LocalFolderStore(root).files()))

    def test_atomic_copy_refuses_a_target_created_after_preview(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.mkdir()
            target.mkdir()
            (source / "note.md").write_text("source", encoding="utf-8")
            (target / "note.md").write_text("late target", encoding="utf-8")

            with self.assertRaisesRegex(
                FolderSyncError, "target_changed_during_sync"
            ):
                LocalFolderStore(target).copy_from(
                    LocalFolderStore(source), "note.md"
                )

            self.assertEqual(
                "late target", (target / "note.md").read_text(encoding="utf-8")
            )


if __name__ == "__main__":
    unittest.main()
