import os
import tempfile
import unittest
from pathlib import Path

from storage.data_sources import (
    FileMoveError,
    list_files,
    list_sources,
    move_file,
    register_source,
    scan_source,
)
from storage.sqlite import initialize


class DataSourceIndexTests(unittest.TestCase):
    def test_register_and_scan_indexes_metadata_without_copying_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            note = root / "notes" / "today.md"
            note.parent.mkdir()
            note.write_text("# Today", encoding="utf-8")
            (root / ".hidden.md").write_text("hidden", encoding="utf-8")

            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            with self._database_override(database):
                source_id = register_source("Demo vault", root)
                self.assertEqual(1, scan_source(source_id))
                files = list_files(source_id)
                self.assertEqual(["notes/today.md"], [item["relative_path"] for item in files])
                self.assertEqual("markdown", files[0]["file_type"])
                self.assertTrue(note.exists())
                self.assertEqual(1, len(list_sources()))

    def test_move_file_updates_disk_and_index_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            source = root / "notes" / "today.md"
            source.parent.mkdir(parents=True)
            source.write_text("# Today", encoding="utf-8")
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)

            with self._database_override(database):
                source_id = register_source("Demo vault", root)
                scan_source(source_id)
                result = move_file(source_id, "notes/today.md", "archive/done.md")

                self.assertEqual("notes/today.md", result.source_path)
                self.assertEqual("archive/done.md", result.destination_path)
                self.assertFalse(source.exists())
                self.assertEqual(
                    ["archive/done.md"],
                    [item["relative_path"] for item in list_files(source_id)],
                )
                (root / "occupied.md").write_text("keep", encoding="utf-8")
                with self.assertRaisesRegex(FileMoveError, "destination_exists"):
                    move_file(source_id, "archive/done.md", "occupied.md")
                self.assertEqual(
                    "keep", (root / "occupied.md").read_text(encoding="utf-8")
                )

    def test_move_file_rejects_absolute_and_parent_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            (root / "note.md").write_text("note", encoding="utf-8")
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)

            with self._database_override(database):
                source_id = register_source("Demo vault", root)
                scan_source(source_id)
                invalid_paths = [
                    str((root / "absolute.md").resolve()),
                    "../outside.md",
                    "notes/../../outside.md",
                    r"C:\outside.md",
                ]
                for destination in invalid_paths:
                    with self.subTest(destination=destination):
                        with self.assertRaisesRegex(
                            FileMoveError, "invalid_relative_path"
                        ):
                            move_file(source_id, "note.md", destination)
                self.assertTrue((root / "note.md").is_file())

    def test_move_file_rolls_back_when_index_refresh_fails(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            source = root / "note.md"
            source.write_text("note", encoding="utf-8")
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)

            with self._database_override(database):
                source_id = register_source("Demo vault", root)
                scan_source(source_id)
                with patch(
                    "storage.data_sources.scan_source",
                    side_effect=RuntimeError("index unavailable"),
                ):
                    with self.assertRaisesRegex(
                        FileMoveError, "file_index_update_failed"
                    ):
                        move_file(source_id, "note.md", "moved.md")
                self.assertTrue(source.is_file())
                self.assertFalse((root / "moved.md").exists())
                self.assertEqual(
                    ["note.md"],
                    [item["relative_path"] for item in list_files(source_id)],
                )

    def test_recent_files_have_stable_order_and_source_sync_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            older = root / "older.md"
            first = root / "a.md"
            second = root / "b.md"
            for path in (older, first, second):
                path.write_text(path.stem, encoding="utf-8")
            os.utime(older, (1_700_000_000, 1_700_000_000))
            os.utime(first, (1_800_000_000, 1_800_000_000))
            os.utime(second, (1_800_000_000, 1_800_000_000))

            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            with self._database_override(database):
                source_id = register_source(
                    "Demo vault",
                    root,
                    source_type="obsidian",
                )
                scan_source(source_id)
                files = list_files(source_id, sort="recent")

                self.assertEqual(
                    ["a.md", "b.md", "older.md"],
                    [item["relative_path"] for item in files],
                )
                self.assertEqual(
                    {"id": source_id, "name": "Demo vault", "type": "obsidian"},
                    files[0]["source"],
                )
                self.assertEqual("2027-01-15T08:00:00.000Z", files[0]["updated_at"])
                self.assertEqual("synced", files[0]["sync_status"])

                first.write_text("changed-size", encoding="utf-8")
                older.unlink()
                statuses = {
                    item["relative_path"]: item["sync_status"]
                    for item in list_files(source_id)
                }
                self.assertEqual("stale", statuses["a.md"])
                self.assertEqual("missing", statuses["older.md"])

    def test_missing_index_metadata_uses_explicit_fallbacks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            note = root / "note.md"
            note.write_text("note", encoding="utf-8")
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            with self._database_override(database):
                source_id = register_source("Demo vault", root)
                scan_source(source_id)
                from storage.sqlite import connect

                with connect(database) as connection:
                    connection.execute(
                        """
                        UPDATE file_records
                        SET modified_at = NULL, content_hash = NULL
                        WHERE data_source_id = ?
                        """,
                        (source_id,),
                    )
                item = list_files(source_id, sort="recent")[0]
                self.assertIsNone(item["updated_at"])
                self.assertEqual("unknown", item["sync_status"])

    def _database_override(self, database: Path):
        from unittest.mock import patch

        from contextlib import ExitStack
        from storage.sqlite import connect

        stack = ExitStack()
        stack.enter_context(patch("storage.data_sources.initialize"))
        stack.enter_context(patch("storage.data_sources.connect", side_effect=lambda path=None: connect(database)))
        return stack


if __name__ == "__main__":
    unittest.main()
