import tempfile
import unittest
from pathlib import Path

from storage.data_sources import list_files, list_sources, register_source, scan_source
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
