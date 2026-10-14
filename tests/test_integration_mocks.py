"""Offline integration tests for provider boundaries."""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
from core.agent import provider as agent_provider
from services.content import global_news
from core.integrations.feishu import idempotency
from services.planning import daily_todo as daily_todo_service
from core.agent.contracts import AgentPlan
from core.integrations.feishu.task_gateway import FeishuTaskGateway
from core.integrations.feishu.gateway import FeishuGateway
from core.integrations.sync_outbox import SyncOutbox
from core.integrations.reconcile import reconcile_pending
from core.runtime import config
from services.communications.chat_analysis import analyze_and_reflect


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload

    def json(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append((request.full_url, timeout))
        return FakeResponse(self.payload)


class FakeHttpSession:
    def post(self, url, **kwargs):
        if "tenant_access_token" in url:
            return FakeResponse({"code": 0, "tenant_access_token": "mock-token"})
        return FakeResponse({"code": 0, "data": {"task": {"id": "task-2"}}})

    def get(self, url, **kwargs):
        return FakeResponse({"code": 0, "data": {"items": []}})

    def delete(self, url, **kwargs):
        return FakeResponse({"code": 0})


class MockIntegrationTests(unittest.TestCase):
    def test_rss_source_is_configured_and_parsed_without_network(self):
        rss = b"""<rss><channel><item>
        <title>Agent release</title><link>https://example.test/a</link>
        <description><![CDATA[New tool &amp; workflow]]></description>
        </item></channel></rss>"""
        opener = FakeOpener(rss)
        with mock.patch.object(global_news.config, "NEWS_WORLD_URLS", ("https://rss.test/feed",)), \
             mock.patch.object(global_news, "translate_and_summarize_world_news",
                                return_value=("Agent 发布", "新增工具")):
            items = global_news.get_world_news(opener=opener)
        self.assertEqual(items[0]["link"], "https://example.test/a")
        self.assertEqual(opener.calls[0][0], "https://rss.test/feed")

    def test_agent_provider_is_mockable_at_single_conversation_boundary(self):
        with mock.patch.object(
            agent_provider.agy_bridge,
            "ask_native_agy",
            return_value='{"todos":["mocked"],"schedule_slots":[]}',
        ) as ask:
            result = agent_provider.ask_json("daily-plan", "plan it", "context")
        self.assertEqual(result["todos"], ["mocked"])
        ask.assert_called_once_with("daily-plan", "plan it", "context")

    def test_chat_analysis_keeps_agent_as_the_semantic_boundary(self):
        private = [{
            "name": "联系人",
            "total_count": 1,
            "my_count": 1,
            "friend_count": 0,
            "time_span": "09:00~09:00",
            "messages": [("09:00", "本人", "明天跟进", "💬")],
        }]
        with mock.patch.object(
            agent_provider,
            "ask_json",
            return_value={
                "private": [{
                    "index": 0,
                    "topics": ["跟进"],
                    "action_items": ["明天跟进"],
                    "reflection": "有明确后续事项",
                }],
                "groups": [],
                "overall": "存在一项明确跟进事项",
            },
        ) as ask:
            result = analyze_and_reflect(private, [], "2026-10-14")
        self.assertEqual(result["compact_privates"][0]["topics"], "跟进")
        self.assertEqual(result["agent_summary"], "存在一项明确跟进事项")
        ask.assert_called_once()

    def test_agent_plan_contract_rejects_invalid_schedule(self):
        with self.assertRaises(ValueError):
            AgentPlan.from_dict({
                "date": "2026-10-14",
                "todos": ["valid"],
                "schedule_slots": [{
                    "name": "bad", "start": "not-time", "end": "10:00",
                    "summary": "invalid",
                }],
            })

    def test_legacy_json_idempotency_store_is_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            sqlite_path = Path(tmp) / "idempotency.sqlite3"
            legacy_path = Path(tmp) / "idempotency.json"
            legacy_path.write_text(
                json.dumps({"legacy-key": {"provider_id": "old-1"}}),
                encoding="utf-8",
            )
            migrated = idempotency.IdempotencyStore(sqlite_path)
            self.assertEqual(migrated.get("legacy-key")["provider_id"], "old-1")
            self.assertTrue((Path(tmp) / "idempotency.json.migrated").exists())

    def test_execute_once_deduplicates_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = idempotency.IdempotencyStore(Path(tmp) / "keys.sqlite3")
            calls = []

            def operation():
                calls.append("called")
                return {"provider_id": "one"}

            first, reused = store.execute_once("same", operation)
            second, reused_again = store.execute_once("same", operation)
            self.assertEqual(first, second)
            self.assertFalse(reused)
            self.assertTrue(reused_again)
            self.assertEqual(calls, ["called"])

    def test_task_sync_reuses_stable_idempotency_key(self):
        class FakeTasks:
            def __init__(self):
                self.created = 0

            def create_task(self, summary, description, due_timestamp=None):
                self.created += 1
                return {"id": "task-1", "summary": summary}

            def list_tasks(self, page_size=50):
                return []

        with tempfile.TemporaryDirectory() as tmp:
            fake_store = idempotency.IdempotencyStore(Path(tmp) / "keys.json")
            fake_tasks = FakeTasks()
            with mock.patch.object(daily_todo_service, "feishu_gateway", fake_tasks), \
                 mock.patch.object(idempotency, "store", fake_store):
                plan = {"date": "2026-10-14", "todos": ["写测试"]}
                self.assertEqual(daily_todo_service.sync_plan_to_feishu_tasks(plan), 1)
                self.assertEqual(daily_todo_service.sync_plan_to_feishu_tasks(plan), 1)
            self.assertEqual(fake_tasks.created, 1)

    def test_feishu_task_gateway_is_offline_mockable(self):
        gateway = FeishuTaskGateway(FakeHttpSession())
        result = gateway.create("mock task", "description")
        self.assertEqual(result["id"], "task-2")
        self.assertEqual(gateway.list(), [])

    def test_feishu_gateway_routes_thread_replies_to_client(self):
        class FakeClient:
            def reply_message(self, message_id, content, msg_type):
                return message_id == "msg-1" and content == {"text": "ok"} and msg_type == "text"

        gateway = FeishuGateway(FakeClient())
        self.assertTrue(gateway.reply_text("msg-1", "ok"))

    def test_reconcile_replays_failed_card_without_duplicate_provider_call(self):
        class FakeClient:
            def __init__(self):
                self.cards = []

            def send_card(self, card):
                self.cards.append(card)
                return True

        with tempfile.TemporaryDirectory() as tmp:
            store = idempotency.IdempotencyStore(Path(tmp) / "keys.sqlite3")
            outbox = SyncOutbox(store)
            key = "card-replay"
            card = {"elements": [{"tag": "div"}]}
            outbox.begin(key, "feishu.card", {"idempotency_key": key, "card": card})
            client = FakeClient()
            gateway = FeishuGateway(client)

            with mock.patch.object(config, "OUTBOX_RETRY_DELAYS_SECONDS", (0,)):
                outbox.finish(key, False, "temporary outage")
                result = reconcile_pending(
                    outbox=outbox, gateway=gateway, idempotency_store=store
                )
                again = reconcile_pending(
                    outbox=outbox, gateway=gateway, idempotency_store=store
                )

            self.assertEqual(result["recovered"], 1)
            self.assertEqual(again["examined"], 0)
            self.assertEqual(client.cards, [card])

    def test_outbox_backoff_and_dead_letter_stop_infinite_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = idempotency.IdempotencyStore(Path(tmp) / "keys.sqlite3")
            outbox = SyncOutbox(store)
            with mock.patch.object(config, "OUTBOX_MAX_ATTEMPTS", 2), \
                 mock.patch.object(config, "OUTBOX_RETRY_DELAYS_SECONDS", (0,)):
                outbox.begin("retry-key", "feishu.task", {"summary": "x"})
                outbox.finish("retry-key", False, "first failure")
                self.assertEqual(len(outbox.pending()), 1)
                outbox.begin("retry-key", "feishu.task", {"summary": "x"})
                outbox.finish("retry-key", False, "second failure")
                self.assertEqual(outbox.pending(), [])
                self.assertEqual(len(outbox.dead_letter()), 1)

    def test_calendar_sync_does_not_delete_unrelated_events(self):
        class FakeCalendar:
            def __init__(self):
                self.cleaned = 0
                self.created = 0

            def clean_day_events(self, _date):
                self.cleaned += 1

            def create_silent_event(self, **_kwargs):
                self.created += 1
                return True, "event-1"

        calendar = FakeCalendar()
        with tempfile.TemporaryDirectory() as tmp:
            fake_store = idempotency.IdempotencyStore(Path(tmp) / "keys.json")
            with mock.patch.object(daily_todo_service.feishu_calendar, "calendar_mgr", calendar), \
                 mock.patch.object(idempotency, "store", fake_store):
                plan = {
                    "date": "2026-10-14",
                    "schedule_slots": [{
                        "name": "专注",
                        "start": "09:00",
                        "end": "10:00",
                        "summary": "专注工作",
                    }],
                }
                daily_todo_service.sync_plan_to_calendar(plan)
                daily_todo_service.sync_plan_to_calendar(plan)
            self.assertEqual(calendar.cleaned, 0)
            self.assertEqual(calendar.created, 1)


if __name__ == "__main__":
    unittest.main()
