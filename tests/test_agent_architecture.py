import tempfile
import unittest
from pathlib import Path

from core.agent.runtime import (
    AgentRequest,
    AgentResponse,
    ProviderCapabilities,
    ProviderError,
)
from core.integrations.channel import ChannelCapabilities, ChannelMessage
from services.subtasks import (
    SubtaskError,
    SubtaskLimits,
    cancel_subtask,
    create_subtask,
    list_subtasks,
    run_pending_subtasks,
)
from storage.sqlite import initialize


class AgentArchitectureTests(unittest.TestCase):
    def test_provider_and_channel_contracts_are_vendor_neutral(self):
        request = AgentRequest("summarize", "prompt", timeout_seconds=10)
        response = AgentResponse("fake", "fake-1", "done", {"ok": True})
        provider = ProviderCapabilities(streaming=True, cancellation=True)
        channel = ChannelCapabilities(images=True, card_updates=True)
        message = ChannelMessage(markdown="**done**")

        self.assertEqual("summarize", request.task)
        self.assertEqual({"ok": True}, response.structured)
        self.assertTrue(provider.cancellation)
        self.assertTrue(channel.card_updates)
        self.assertEqual("**done**", message.markdown)
        self.assertTrue(ProviderError("timeout", retryable=True).retryable)

    def test_subtasks_are_idempotent_bounded_persistent_and_cancellable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            first = create_subtask(
                "parent-1",
                "double",
                {"value": 2},
                idempotency_key="parent-1:double:2",
                database_path=database,
            )
            duplicate = create_subtask(
                "parent-1",
                "double",
                {"value": 2},
                idempotency_key="parent-1:double:2",
                database_path=database,
            )
            cancelled = create_subtask(
                "parent-1",
                "double",
                {"value": 3},
                idempotency_key="parent-1:double:3",
                database_path=database,
            )
            self.assertEqual(first["id"], duplicate["id"])
            self.assertTrue(cancel_subtask(cancelled["id"], database_path=database))

            tasks = run_pending_subtasks(
                {"double": lambda payload: {"value": payload["value"] * 2}},
                parent_id="parent-1",
                database_path=database,
                limits=SubtaskLimits(max_concurrency=2),
            )
            by_id = {task["id"]: task for task in tasks}
            self.assertEqual("completed", by_id[first["id"]]["status"])
            self.assertEqual({"value": 4}, by_id[first["id"]]["result"])
            self.assertEqual("cancelled", by_id[cancelled["id"]]["status"])

    def test_subtask_depth_and_count_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            limits = SubtaskLimits(max_depth=1, max_tasks=1)
            with self.assertRaisesRegex(SubtaskError, "depth"):
                create_subtask(
                    "parent",
                    "task",
                    {},
                    depth=2,
                    idempotency_key="too-deep",
                    database_path=database,
                    limits=limits,
                )
            create_subtask(
                "parent",
                "task",
                {},
                idempotency_key="first",
                database_path=database,
                limits=limits,
            )
            with self.assertRaisesRegex(SubtaskError, "limit"):
                create_subtask(
                    "parent",
                    "task",
                    {},
                    idempotency_key="second",
                    database_path=database,
                    limits=limits,
                )

    def test_missing_handler_records_a_failed_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            create_subtask(
                "parent",
                "missing",
                {},
                idempotency_key="missing-handler",
                database_path=database,
            )
            tasks = run_pending_subtasks(
                {},
                parent_id="parent",
                database_path=database,
            )
            self.assertEqual("failed", tasks[0]["status"])
            self.assertEqual("subtask_handler_not_found", tasks[0]["error_message"])
            self.assertEqual(
                tasks,
                list_subtasks("parent", database_path=database),
            )


if __name__ == "__main__":
    unittest.main()
