"""Offline integration tests for provider boundaries."""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "services"))

import agent_provider
import global_news
import idempotency
import daily_todo_service
from contracts import AgentPlan
from feishu_task_gateway import FeishuTaskGateway


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
