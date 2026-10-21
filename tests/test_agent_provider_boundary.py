import os
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock

from core.agent.runtime import AgentProvider, AgentRequest, AgentResponse, ProviderCapabilities, ProviderError, ProviderHealth
from services.agent_requests import AgentRequestService
from storage import agent_requests as request_repo
from storage.sqlite import initialize
from server.progress import ProgressController, progress_controller
from server.message_processor import process_message


class FakeAgentProvider:
    name = "fake"
    capabilities = ProviderCapabilities(streaming=False, images=False)

    def __init__(self, reply_text: str = "Fake answer", delay: float = 0.0, raise_error: Exception = None):
        self.reply_text = reply_text
        self.delay = delay
        self.raise_error = raise_error
        self.invoked_ids = []
        self.cancelled_ids = []

    def invoke(self, request_id: str, request: AgentRequest, cancel_event: threading.Event = None) -> AgentResponse:
        self.invoked_ids.append(request_id)
        if self.delay > 0:
            step = 0.02
            elapsed = 0.0
            while elapsed < self.delay:
                if cancel_event and cancel_event.is_set():
                    raise ProviderError(f"Cancelled by token for request {request_id}")
                time.sleep(step)
                elapsed += step
        if cancel_event and cancel_event.is_set():
            raise ProviderError(f"Cancelled by token for request {request_id}")
        if self.raise_error:
            raise self.raise_error
        return AgentResponse(provider=self.name, model="mock-model", text=self.reply_text)

    def cancel(self, request_id: str) -> bool:
        self.cancelled_ids.append(request_id)
        return True

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=True, status="healthy")


class TestAgentProviderBoundary(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        initialize(self.db_path)
        self.fake_provider = FakeAgentProvider(reply_text="Hello from FakeProvider!")
        self.service = AgentRequestService(
            provider=self.fake_provider,
            database_path=self.db_path,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normal_lifecycle_transition(self):
        """Test normal happy path: pending -> running -> completed."""
        req_id, is_new = self.service.create_request(
            source_message_id="msg_001",
            prompt="What is the weather?",
            context="user_ctx",
        )
        self.assertTrue(is_new)
        self.assertTrue(req_id.startswith("req_"))

        req_row = request_repo.get_agent_request(req_id, database_path=self.db_path)
        self.assertEqual(req_row["status"], "pending")

        reply, ok = self.service.execute_request(req_id)
        self.assertTrue(ok)
        self.assertEqual(reply, "Hello from FakeProvider!")

        final_row = request_repo.get_agent_request(req_id, database_path=self.db_path)
        self.assertEqual(final_row["status"], "completed")
        self.assertEqual(final_row["result_text"], "Hello from FakeProvider!")
        self.assertIsNotNone(final_row["finished_at"])

    def test_provider_error_transitions_to_failed(self):
        """Test provider failure (503/timeout): running -> failed."""
        self.fake_provider.raise_error = ProviderError("503 Service Unavailable")
        req_id, _ = self.service.create_request(
            source_message_id="msg_002",
            prompt="Crash please",
        )
        reply, ok = self.service.execute_request(req_id)
        self.assertFalse(ok)
        self.assertIn("503 Service Unavailable", reply)

        row = request_repo.get_agent_request(req_id, database_path=self.db_path)
        self.assertEqual(row["status"], "failed")
        self.assertIn("503 Service Unavailable", row["error"])

    def test_idempotent_duplicate_message_creation(self):
        """Duplicate message events with same source_message_id should not create duplicate rows."""
        id1, is_new1 = self.service.create_request(
            source_message_id="msg_dup_100",
            prompt="Hello",
        )
        self.assertTrue(is_new1)

        id2, is_new2 = self.service.create_request(
            source_message_id="msg_dup_100",
            prompt="Hello duplicate",
        )
        self.assertFalse(is_new2)
        self.assertEqual(id1, id2)

    def test_cancel_by_source_message(self):
        """Recalling/cancelling source message marks status as cancelled."""
        req_id, _ = self.service.create_request(
            source_message_id="msg_cancel_001",
            prompt="To be cancelled",
        )
        # Transition to running
        request_repo.mark_request_running(req_id, database_path=self.db_path)

        cancelled = self.service.cancel_by_source_message("msg_cancel_001")
        self.assertEqual(cancelled, [req_id])
        self.assertIn(req_id, self.fake_provider.cancelled_ids)

        row = request_repo.get_agent_request(req_id, database_path=self.db_path)
        self.assertEqual(row["status"], "cancelled")
        self.assertIsNotNone(row["cancel_requested_at"])

    def test_race_condition_provider_finishes_after_cancellation(self):
        """When user cancels during provider invoke, SQLite must drop the response and NOT overwrite cancelled status."""
        self.fake_provider.delay = 0.2
        req_id, _ = self.service.create_request(
            source_message_id="msg_race_001",
            prompt="Long running prompt",
        )

        def delayed_cancel():
            time.sleep(0.05)
            self.service.cancel_by_source_message("msg_race_001")

        t = threading.Thread(target=delayed_cancel)
        t.start()

        reply, ok = self.service.execute_request(req_id)
        t.join()

        self.assertFalse(ok)
        self.assertIn("取消", reply)

        row = request_repo.get_agent_request(req_id, database_path=self.db_path)
        self.assertEqual(row["status"], "cancelled")
        # Ensure result_text is None and was not overwritten
        self.assertIsNone(row["result_text"])

    def test_startup_recover_interrupted_requests(self):
        """Requests left in 'running' state upon crash/restart must be marked 'interrupted'."""
        req_id1, _ = self.service.create_request(source_message_id="msg_rec_1", prompt="p1")
        req_id2, _ = self.service.create_request(source_message_id="msg_rec_2", prompt="p2")
        req_id3, _ = self.service.create_request(source_message_id="msg_rec_3", prompt="p3")

        # Mark 1 and 2 as running
        request_repo.mark_request_running(req_id1, database_path=self.db_path)
        request_repo.mark_request_running(req_id2, database_path=self.db_path)
        # req_id3 stays pending

        recovered = self.service.recover_interrupted_requests()
        self.assertEqual(recovered, 2)

        row1 = request_repo.get_agent_request(req_id1, database_path=self.db_path)
        self.assertEqual(row1["status"], "interrupted")
        self.assertIn("server_restarted", row1["error"])

        row3 = request_repo.get_agent_request(req_id3, database_path=self.db_path)
        self.assertEqual(row3["status"], "pending")

    def test_end_to_end_message_processor_with_recalled_flow(self):
        """Integration test with message_processor: verify card progress starts and cancellation terminates animation."""
        updates = []
        def dummy_update(reply_msg_id, content, title="", template=""):
            updates.append({"id": reply_msg_id, "content": content, "title": title, "template": template})
            return True

        replies = []
        def dummy_reply(source_msg_id, content, title="", template=""):
            rep_id = f"reply_for_{source_msg_id}"
            replies.append({"id": rep_id, "source": source_msg_id, "content": content})
            return rep_id

        # Use a provider with 0.15s delay
        self.fake_provider.delay = 0.15
        from services.agent_requests import agent_request_service
        # Temporarily patch global service
        old_provider = agent_request_service._provider
        old_db = agent_request_service._database_path
        agent_request_service.set_provider(self.fake_provider)
        agent_request_service._database_path = self.db_path

        try:
            # Trigger message processing in background
            t = threading.Thread(
                target=process_message,
                args=("user_123", "Hello AGY", "feishu_msg_e2e_1"),
                kwargs=dict(
                    todo_handler=lambda text: None,
                    get_images=lambda open_id: [],
                    archive_lifestyle=lambda *a, **kw: None,
                    reply=dummy_reply,
                    update=dummy_update,
                    gather_context=lambda text: "test context",
                    ask_agent=lambda prompt, ctx, msg_id: "legacy",
                    animate=lambda rid, ev: None,
                    stop_animation=lambda: None,
                    event_fn=lambda *a, **kw: None,
                    logger=MagicMock(),
                )
            )
            t.start()

            # Wait briefly for request to register and start progress
            time.sleep(0.04)
            # User recalls message in Feishu!
            cancelled_ids = agent_request_service.cancel_by_source_message("feishu_msg_e2e_1")
            self.assertEqual(len(cancelled_ids), 1)

            t.join()

            # Verify that card was updated to terminal grey cancelled state
            cancelled_updates = [u for u in updates if "已撤回" in u["content"]]
            self.assertTrue(len(cancelled_updates) > 0, f"Expected cancellation update, got: {updates}")
            self.assertEqual(cancelled_updates[-1]["template"], "grey")
        finally:
            agent_request_service.set_provider(old_provider)
            agent_request_service._database_path = old_db


if __name__ == "__main__":
    unittest.main()
