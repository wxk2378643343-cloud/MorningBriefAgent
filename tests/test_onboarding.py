import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from storage.onboarding import complete_step, get_status, reset_step, skip_step
from storage.sqlite import connect, initialize


class OnboardingStateTests(unittest.TestCase):
    def test_status_starts_at_workspace(self):
        with self._database() as database:
            status = get_status(database)
            self.assertEqual(status["current_step"], "workspace")
            self.assertEqual(status["completed_count"], 0)

    def test_steps_are_local_and_reversible(self):
        with self._database() as database:
            complete_step("workspace", detail="local workspace initialized", database_path=database)
            complete_step("provider", detail="deepseek", database_path=database)
            status = get_status(database)
            self.assertEqual(status["current_step"], "channel")
            self.assertFalse(status["complete"])
            reset_step("provider", database_path=database)
            self.assertEqual(get_status(database)["current_step"], "provider")

    def test_unknown_step_is_rejected(self):
        with self._database() as database:
            with self.assertRaises(ValueError):
                complete_step("secrets", database_path=database)

    def test_legacy_skipped_steps_are_migrated_back_to_pending(self):
        with self._database() as database:
            complete_step("workspace", detail="initialized", database_path=database)
            skip_step("provider", detail="later", database_path=database)
            skip_step("channel", detail="later", database_path=database)
            skip_step("profile", detail="later", database_path=database)
            status = get_status(database)
            self.assertFalse(status["complete"])
            self.assertEqual(status["completed_count"], 1)
            self.assertEqual(status["skipped_count"], 0)
            self.assertEqual(status["current_step"], "provider")

    def _database(self):
        temp_dir = tempfile.TemporaryDirectory()
        database = Path(temp_dir.name) / "app.sqlite3"
        initialize(database)
        stack = ExitStack()
        stack.enter_context(patch("storage.onboarding.initialize"))
        stack.enter_context(
            patch(
                "storage.onboarding.connect",
                side_effect=lambda path=None: connect(database),
            )
        )
        stack.temp_dir = temp_dir
        stack.database = database
        return _Context(stack, database)


class _Context:
    def __init__(self, stack, database):
        self.stack = stack
        self.database = database

    def __enter__(self):
        self.stack.__enter__()
        return self.database

    def __exit__(self, *args):
        self.stack.__exit__(*args)
        self.stack.temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
