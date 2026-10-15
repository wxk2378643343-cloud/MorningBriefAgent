import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage.bootstrap import (
    get_installation_state,
    initialize_workspace,
    mark_setup_complete,
)
from storage.sqlite import connect, initialize


class WorkspaceBootstrapTests(unittest.TestCase):
    def test_initialization_is_local_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "workspace"
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            with self._database_override(database):
                first = initialize_workspace(root, database_path=database)
                second = initialize_workspace(root, database_path=database)
                self.assertEqual(len(first["created_directories"]), 10)
                self.assertEqual(second["created_directories"], [])
                self.assertTrue((root / "knowledge" / "profile").is_dir())
                self.assertEqual(get_installation_state()["workspace_root"], str(root.resolve()))

    def test_setup_completion_records_provider_and_channel(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            with self._database_override(database):
                mark_setup_complete(
                    provider="deepseek",
                    channel="feishu",
                    database_path=database,
                )
                state = get_installation_state(database)
                self.assertEqual(state["completed"], 1)
                self.assertEqual(state["selected_provider"], "deepseek")
                self.assertEqual(state["selected_channel"], "feishu")

    def _database_override(self, database: Path):
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(patch("storage.bootstrap.initialize"))
        stack.enter_context(
            patch(
                "storage.bootstrap.connect",
                side_effect=lambda path=None: connect(database),
            )
        )
        return stack


if __name__ == "__main__":
    unittest.main()
