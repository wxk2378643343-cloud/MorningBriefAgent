"""Offline integration tests for provider boundaries."""

import io
import datetime
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
import main as cli
from core.agent import agy_bridge
from core.agent import context as agent_context
from core.agent import provider as agent_provider
from services.content import global_news, inspect_and_brief
from core.integrations.feishu import idempotency
from services.planning import daily_todo as daily_todo_service
from core.agent.contracts import AgentPlan
from core.integrations.feishu.task_gateway import FeishuTaskGateway
from core.integrations.feishu.gateway import FeishuGateway
from core.integrations.sync_outbox import SyncOutbox
from core.integrations.reconcile import reconcile_pending
from core.runtime import config
from core.runtime.observability import redact_sensitive_text
from services.communications import chat_reader
from services.finance import fund_advisor
from services.lifestyle import feishu_archive
from services.lifestyle import fitness_daily
from services.planning import calendar_sync as calendar_sync_service
from services.planning import feishu_tasks as feishu_tasks_service
from services.planning import review_sync
from services.planning import todo_analysis
from services.communications.chat_analysis import (
    _build_agent_batches,
    analyze_and_reflect,
)
from server import feishu_bot_server


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
    def test_context_vault_fallback_is_explicit_and_keeps_multiple_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.md").write_text("今日计划 A" * 500, encoding="utf-8")
            (root / "two.md").write_text("今日待办 B" * 500, encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {
                    "VAULT_ROOT": str(root),
                    "AGENT_CONTEXT_FILES": "",
                    "AGENT_CONTEXT_DIRS": "",
                },
            ):
                default_documents = agent_context.collect_context_documents(
                    "今日 计划 待办", max_files=2, max_chars=2000
                )
                documents = agent_context.collect_context_documents(
                    "今日 计划 待办",
                    max_files=2,
                    max_chars=2000,
                    fallback_dirs=(root,),
                )
        self.assertEqual(default_documents, [])
        self.assertEqual(len(documents), 2)
        self.assertEqual(sum(len(item["excerpt"]) for item in documents), 2000)

    def test_todo_fact_analysis_rejects_untraceable_agent_items(self):
        response = {
            "valid_items": [
                {
                    "title": "跟进项目",
                    "source_text": "明天跟进项目",
                    "confidence": 0.9,
                    "reason": "明确承诺",
                },
                {
                    "title": "凭空任务",
                    "source_text": "不存在的原句",
                    "confidence": 0.99,
                },
            ],
            "rejected_items": [],
            "constraints": [],
        }
        with mock.patch.object(agent_provider, "ask_json", return_value=response):
            result = todo_analysis.analyze_candidates(["明天跟进项目"], "2026-10-16")
        self.assertEqual(
            [item["title"] for item in result["valid_items"]],
            ["跟进项目"],
        )

    def test_empty_content_fails_quality_gate(self):
        news_quality = global_news.evaluate_news_quality(
            {"domestic": [], "world": []}, []
        )
        brief_quality = inspect_and_brief.evaluate_brief_quality(
            {"documents": [], "emails": []}
        )
        self.assertFalse(news_quality.ready)
        self.assertFalse(brief_quality.ready)

    def test_lifestyle_archive_classifies_records_but_not_plan_questions(self):
        self.assertEqual(
            feishu_archive.classify_lifestyle_record("牛肉面加牛肉 今天中午饭"),
            "午餐",
        )
        self.assertEqual(
            feishu_archive.classify_lifestyle_record("这是我今天训练成果"),
            "训练打卡",
        )
        self.assertIsNone(
            feishu_archive.classify_lifestyle_record("今天健身计划是什么？")
        )
        self.assertIsNone(
            feishu_archive.classify_lifestyle_record("香蕉热量多少？")
        )
        self.assertEqual(
            feishu_archive.classify_lifestyle_record(
                "这个早餐怎么样？", has_images=True
            ),
            "早餐",
        )

    def test_lifestyle_archive_copies_image_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_dir = root / "fitness"
            source = root / "meal.jpg"
            source.write_bytes(b"fake-image")
            when = datetime.datetime(2026, 10, 14, 8, 27, 13)
            with mock.patch.object(
                feishu_archive.config,
                "FITNESS_ARCHIVE_DIR",
                str(archive_dir),
            ), mock.patch.object(
                feishu_archive.config,
                "PROJECT_ROOT",
                root,
            ):
                first = feishu_archive.archive_lifestyle_message(
                    "今天早餐",
                    "om_breakfast",
                    [str(source)],
                    now=when,
                )
                second = feishu_archive.archive_lifestyle_message(
                    "今天早餐",
                    "om_breakfast",
                    [str(source)],
                    now=when,
                )

            self.assertFalse(first["duplicate"])
            self.assertTrue(second["duplicate"])
            note = Path(first["note_path"]).read_text(encoding="utf-8")
            self.assertEqual(note.count("<!-- feishu-message:om_breakfast -->"), 1)
            self.assertIn("## 08:27 · 早餐", note)
            self.assertIn("![早餐](2026-10-14/", note)
            self.assertEqual(len(list((archive_dir / "2026-10-14").iterdir())), 1)

    def test_fitness_publisher_does_not_overwrite_feishu_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_dir = Path(tmp)
            note = archive_dir / "2026-10-14-训练课表推送与执行记录.md"
            original = (
                "# existing\n\n"
                "<!-- feishu-message:om_breakfast -->\n"
                "## 08:27 · 早餐\n"
            )
            note.write_text(original, encoding="utf-8")
            workout = {
                "weekday_str": "Wednesday",
                "muscle_group": "恢复",
                "exercises": [],
            }
            fixed_date = datetime.date(2026, 10, 14)
            with mock.patch.object(
                fitness_daily.config,
                "FITNESS_ARCHIVE_DIR",
                str(archive_dir),
            ), mock.patch.object(
                fitness_daily.datetime,
                "date",
            ) as fake_date:
                fake_date.today.return_value = fixed_date
                fitness_daily.record_fitness_to_obsidian(workout)

            self.assertEqual(note.read_text(encoding="utf-8"), original)

    def test_log_redaction_removes_connection_credentials(self):
        message = (
            "connected to wss://example.test/ws?"
            "access_key=secret-access&ticket=secret-ticket "
            "Authorization: Bearer secret-token csrf_token=secret-csrf"
        )
        redacted = redact_sensitive_text(message)
        for secret in (
            "secret-access",
            "secret-ticket",
            "secret-token",
            "secret-csrf",
        ):
            self.assertNotIn(secret, redacted)
        self.assertGreaterEqual(redacted.count("<redacted>"), 4)

    def test_shared_agy_conversation_is_serialized(self):
        active = 0
        maximum_active = 0
        state_lock = threading.Lock()
        start = threading.Barrier(2)

        def fake_call(*_args):
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.05)
            with state_lock:
                active -= 1
            return "ok"

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            agy_bridge.config, "PROJECT_ROOT", Path(tmp)
        ), mock.patch.object(
            agy_bridge, "_ask_native_agy_locked", side_effect=fake_call
        ):
            results = []

            def worker():
                start.wait()
                results.append(agy_bridge.ask_native_agy("user", "prompt"))

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)

        self.assertEqual(results, ["ok", "ok"])
        self.assertEqual(maximum_active, 1)

    def test_file_lock_serializes_separate_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "shared.lock"
            events_path = Path(tmp) / "events.txt"
            code = (
                "import sys,time;"
                "from pathlib import Path;"
                "from core.runtime.locking import CrossProcessFileLock;"
                "lock=Path(sys.argv[1]);events=Path(sys.argv[2]);"
                "guard=CrossProcessFileLock(lock,timeout=5);"
                "guard.acquire();"
                "f=events.open('a',encoding='utf-8');"
                "f.write('acquire\\n');f.close();"
                "time.sleep(0.15);"
                "f=events.open('a',encoding='utf-8');"
                "f.write('release\\n');f.close();"
                "guard.release()"
            )
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", code, str(lock_path), str(events_path)],
                    cwd=ROOT,
                )
                for _ in range(2)
            ]
            for process in processes:
                self.assertEqual(process.wait(timeout=5), 0)

            self.assertEqual(
                events_path.read_text(encoding="utf-8").splitlines(),
                ["acquire", "release", "acquire", "release"],
            )

    def test_cli_runtime_entrypoints_delegate_to_public_services(self):
        with mock.patch.object(
            daily_todo_service, "morning_routine", return_value=True
        ) as morning:
            cli.run_todo_morning()
        with mock.patch.object(
            daily_todo_service, "evening_routine", return_value=True
        ) as evening:
            cli.run_todo_evening()
        with mock.patch.object(
            feishu_bot_server, "start_bot", return_value=None
        ) as bot:
            cli.run_bot()

        morning.assert_called_once_with()
        evening.assert_called_once_with()
        bot.assert_called_once_with()

    def test_evening_review_saves_plan_and_sends_card(self):
        analysis = {
            "target_date": "2026-10-15",
            "valid_items": [{
                "title": "跟进事项",
                "source_text": "跟进事项",
                "confidence": 0.9,
                "reason": "明确行动",
            }],
            "rejected_items": [],
            "constraints": [],
        }
        with mock.patch.object(
            daily_todo_service, "extract_candidates_from_chat", return_value=["跟进事项"]
        ), mock.patch.object(
            daily_todo_service.todo_analysis, "analyze_candidates", return_value=analysis
        ), mock.patch.object(
            daily_todo_service,
            "generate_agent_plan",
            return_value={
                "date": "2026-10-15",
                "todos": ["跟进事项"],
                "schedule_slots": [],
            },
        ), mock.patch.object(
            daily_todo_service, "save_staged_plan"
        ) as save_plan, mock.patch.object(
            daily_todo_service, "push_feishu_card", return_value=True
        ) as push_card:
            self.assertTrue(daily_todo_service.evening_routine())

        saved = save_plan.call_args.args[0]
        self.assertEqual(saved["todos"], ["跟进事项"])
        self.assertEqual(saved["analysis"], analysis)
        self.assertFalse(saved["confirmed"])
        self.assertEqual(push_card.call_count, 1)

    def test_evening_confirmation_branch_is_reachable(self):
        class EveningDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 14, 22, 0, 0, tzinfo=tz)

        plan = {
            "date": "2026-10-15",
            "todos": ["跟进事项"],
            "schedule_slots": [],
            "confirmed": False,
        }
        with mock.patch.object(
            daily_todo_service.datetime, "datetime", EveningDateTime
        ), mock.patch.object(
            daily_todo_service, "load_staged_plan", return_value=plan
        ), mock.patch.object(
            daily_todo_service, "save_staged_plan"
        ) as save_plan, mock.patch.object(
            daily_todo_service, "sync_plan_to_calendar", return_value=2
        ) as sync_calendar, mock.patch.object(
            daily_todo_service, "sync_plan_to_feishu_tasks", return_value=1
        ) as sync_tasks:
            reply = daily_todo_service.handle_todo_intent("确认排期")

        self.assertIn("飞书官方日历", reply)
        self.assertTrue(plan["confirmed"])
        save_plan.assert_called_once_with(plan)
        sync_calendar.assert_called_once_with(plan)
        sync_tasks.assert_called_once_with(plan)

    def test_rss_source_is_configured_and_parsed_without_network(self):
        rss = b"""<rss><channel><item>
        <title>Agent release</title><link>https://example.test/a</link>
        <description><![CDATA[New tool &amp; workflow]]></description>
        </item></channel></rss>"""
        opener = FakeOpener(rss)
        with mock.patch.object(global_news.config, "NEWS_WORLD_URLS", ("https://rss.test/feed",)), \
             mock.patch.object(
                 global_news,
                 "normalize_world_news_batch",
                 side_effect=lambda items: [{
                     "title": "Agent 发布",
                     "en_title": items[0]["title"],
                     "link": items[0]["link"],
                     "desc": "新增工具",
                 }],
             ):
            items = global_news.get_world_news(opener=opener)
        self.assertEqual(items[0]["link"], "https://example.test/a")
        self.assertEqual(opener.calls[0][0], "https://rss.test/feed")

    def test_global_market_quote_uses_percentage_field(self):
        opener = FakeOpener(
            b'var hq_str_gb_$aapl="Apple,190.50,0.66,2026-10-14 16:13:45,1.25,189.25,191.00";'
        )
        with mock.patch.object(
            fund_advisor.urllib.request,
            "build_opener",
            return_value=opener,
        ):
            quotes = fund_advisor.fetch_realtime_quotes(["gb_$aapl"])
        self.assertEqual(quotes["gb_$aapl"]["price"], 190.50)
        self.assertEqual(quotes["gb_$aapl"]["change_pct"], 0.66)

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

    def test_chat_analysis_batches_preserve_every_selected_message(self):
        private_messages = [
            (f"{index // 60:02d}:{index % 60:02d}", "本人", "较长消息" * 20, "💬")
            for index in range(180)
        ]
        group_messages = [
            ("10:00", "群友", "群聊内容" * 20, "💬") for _ in range(40)
        ]
        batches = _build_agent_batches(
            [{
                "name": "联系人",
                "time_span": "00:00~02:59",
                "messages": private_messages,
            }],
            [{
                "name": "群聊",
                "messages": group_messages,
                "my_messages": [],
                "other_messages": group_messages,
            }],
            "2026-10-14",
        )
        included_private = sum(
            len(item["messages"])
            for batch in batches
            for item in batch["private"]
        )
        included_groups = sum(
            len(item["messages"])
            for batch in batches
            for item in batch["groups"]
        )
        self.assertGreater(len(batches), 1)
        self.assertEqual(included_private, len(private_messages))
        self.assertEqual(included_groups, len(group_messages))
        self.assertLessEqual(
            max(len(json.dumps(batch, ensure_ascii=False)) for batch in batches),
            20000,
        )

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

    def test_execute_once_deduplicates_concurrent_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = idempotency.IdempotencyStore(Path(tmp) / "keys.sqlite3")
            calls = []
            start = threading.Barrier(2)
            results = []

            def operation():
                calls.append("called")
                time.sleep(0.05)
                return {"provider_id": "one"}

            def worker():
                start.wait()
                results.append(store.execute_once("same", operation))

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)

            self.assertEqual(calls, ["called"])
            self.assertEqual(len(results), 2)
            self.assertEqual(sorted(reused for _, reused in results), [False, True])

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
            fake_outbox = SyncOutbox(fake_store)
            fake_tasks = FakeTasks()
            with mock.patch.object(daily_todo_service, "feishu_gateway", fake_tasks), \
                 mock.patch.object(idempotency, "store", fake_store), \
                 mock.patch.object(feishu_tasks_service, "sync_outbox", fake_outbox):
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
                if message_id == "msg-1" and content == {"text": "ok"} and msg_type == "text":
                    return "om-reply"
                return None

            def update_card(self, message_id, card):
                return message_id == "om-reply" and card == {"elements": []}

        gateway = FeishuGateway(FakeClient())
        self.assertEqual(gateway.reply_text("msg-1", "ok"), "om-reply")
        self.assertTrue(gateway.update_card("om-reply", {"elements": []}))

    def test_bot_streams_progress_and_final_into_one_reply_card(self):
        with mock.patch.object(
            feishu_bot_server.daily_todo_service,
            "handle_todo_intent",
            return_value=None,
        ), mock.patch.object(
            feishu_bot_server,
            "get_and_clear_user_images",
            return_value=[],
        ), mock.patch.object(
            feishu_bot_server.feishu_archive,
            "archive_lifestyle_message",
            return_value=None,
        ), mock.patch.object(
            feishu_bot_server,
            "gather_agent_context",
            return_value="context",
        ), mock.patch.object(
            feishu_bot_server.agent_provider.agy_bridge,
            "ask_native_agy",
            return_value="最终回答",
        ), mock.patch.object(
            feishu_bot_server,
            "reply_feishu_message",
            return_value="om-progress",
        ) as reply_message, mock.patch.object(
            feishu_bot_server,
            "update_feishu_reply",
            return_value=True,
        ) as update_reply:
            feishu_bot_server.process_message_async(
                "ou-user",
                "请分析今天的安排",
                "om-user-message",
            )

        self.assertEqual(reply_message.call_count, 1)
        self.assertEqual(update_reply.call_count, 2)
        self.assertEqual(update_reply.call_args_list[-1].args[0], "om-progress")
        self.assertEqual(update_reply.call_args_list[-1].args[1], "最终回答")

    def test_thinking_animation_rotates_one_card_until_stopped(self):
        class StopAfterOneFrame:
            def __init__(self):
                self.calls = 0

            def wait(self, _seconds):
                self.calls += 1
                return self.calls > 1

        with mock.patch.object(
            feishu_bot_server,
            "update_feishu_reply",
            return_value=True,
        ) as update_reply:
            feishu_bot_server.animate_thinking_reply(
                "om-progress",
                StopAfterOneFrame(),
            )

        update_reply.assert_called_once()
        self.assertEqual(update_reply.call_args.args[0], "om-progress")
        self.assertIn("✦ · ·  Agent 正在深度分析", update_reply.call_args.args[1])

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

    def test_reconcile_counts_card_replays_until_dead_letter(self):
        class FailingClient:
            def __init__(self):
                self.calls = 0

            def send_card(self, _card):
                self.calls += 1
                return False

        with tempfile.TemporaryDirectory() as tmp:
            store = idempotency.IdempotencyStore(Path(tmp) / "keys.sqlite3")
            outbox = SyncOutbox(store)
            key = "always-failing-card"
            client = FailingClient()
            gateway = FeishuGateway(client)

            with mock.patch.object(config, "OUTBOX_MAX_ATTEMPTS", 3), \
                 mock.patch.object(config, "OUTBOX_RETRY_DELAYS_SECONDS", (0,)):
                owner = outbox.begin(
                    key,
                    "feishu.card",
                    {"card": {"elements": []}},
                )
                outbox.finish(
                    key,
                    False,
                    "initial failure",
                    lease_owner=owner,
                )
                first = reconcile_pending(
                    outbox=outbox, gateway=gateway, idempotency_store=store
                )
                second = reconcile_pending(
                    outbox=outbox, gateway=gateway, idempotency_store=store
                )

            self.assertEqual(first["failed"], 1)
            self.assertEqual(second["failed"], 1)
            self.assertEqual(client.calls, 2)
            self.assertEqual(outbox.pending(), [])
            self.assertEqual(len(outbox.dead_letter()), 1)

    def test_outbox_claim_is_exclusive_until_lease_expires(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = idempotency.IdempotencyStore(Path(tmp) / "keys.sqlite3")
            outbox = SyncOutbox(store)
            with mock.patch.object(config, "OUTBOX_RETRY_DELAYS_SECONDS", (0,)):
                owner = outbox.begin("leased", "feishu.card", {"card": {}})
                outbox.finish("leased", False, "retry", lease_owner=owner)

            first = outbox.claim_due(lease_seconds=30)
            second = outbox.claim_due(lease_seconds=30)

            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])

    def test_stale_outbox_worker_cannot_overwrite_new_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = idempotency.IdempotencyStore(Path(tmp) / "keys.sqlite3")
            outbox = SyncOutbox(store)
            old_owner = outbox.begin("stale", "feishu.card", {"card": {}})
            with closing(sqlite3.connect(str(store.path))) as connection:
                connection.execute(
                    "UPDATE sync_outbox SET lease_until = ? WHERE key = ?",
                    ("2000-01-01T00:00:00+00:00", "stale"),
                )
                connection.commit()

            claimed = outbox.claim_due(lease_seconds=30)
            self.assertEqual(len(claimed), 1)
            new_owner = claimed[0]["lease_owner"]
            self.assertNotEqual(old_owner, new_owner)
            self.assertFalse(
                outbox.finish("stale", True, lease_owner=old_owner)
            )
            self.assertTrue(
                outbox.finish("stale", True, lease_owner=new_owner)
            )

    def test_outbox_purges_only_old_succeeded_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = idempotency.IdempotencyStore(Path(tmp) / "keys.sqlite3")
            outbox = SyncOutbox(store)
            outbox.begin("old-success", "feishu.task", {"summary": "x"})
            outbox.finish("old-success", True)
            with closing(sqlite3.connect(str(store.path))) as connection:
                connection.execute(
                    "UPDATE sync_outbox SET updated_at = ? WHERE key = ?",
                    ("2000-01-01T00:00:00+00:00", "old-success"),
                )
                connection.commit()
            self.assertEqual(outbox.purge_succeeded(retention_days=30), 1)
            self.assertEqual(outbox.dead_letter(), [])

    def test_chat_reader_scans_configured_sqlite_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contact_db = root / "contact.db"
            message_db = root / "message.db"
            username = "wxid_alice"
            group = "team@chatroom"
            private_table = f"Msg_{hashlib.md5(username.encode()).hexdigest()}"
            group_table = f"Msg_{hashlib.md5(group.encode()).hexdigest()}"
            with closing(sqlite3.connect(str(contact_db))) as connection:
                connection.execute(
                    "CREATE TABLE contact(username TEXT, remark TEXT, nick_name TEXT)"
                )
                connection.executemany(
                    "INSERT INTO contact VALUES (?, ?, ?)",
                    [(username, "Alice", "Alice N"), (group, "", "Team")],
                )
                connection.commit()
            with closing(sqlite3.connect(str(message_db))) as connection:
                for table in (private_table, group_table):
                    connection.execute(
                        f"CREATE TABLE {table}("
                        "create_time INTEGER, status INTEGER, local_type INTEGER, "
                        "message_content TEXT)"
                    )
                connection.execute(
                    f"INSERT INTO {private_table} VALUES (100, 2, 1, '跟进事项')"
                )
                connection.execute(
                    f"INSERT INTO {group_table} VALUES (100, 2, 1, '群内更新')"
                )
                connection.commit()
            friends, groups = chat_reader.get_contact_maps(str(contact_db))
            private = chat_reader.scan_private_chats(str(message_db), friends, 0, 200)
            selected, total = chat_reader.scan_target_group_chats(
                str(message_db), groups, 0, 200, ("Team",)
            )
            self.assertEqual(friends[username], "Alice")
            self.assertEqual(private[0]["messages"][0][2], "跟进事项")
            self.assertEqual(selected[0]["name"], "Team")
            self.assertEqual(total, 1)

    def test_review_facade_creates_weekly_and_monthly_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.multiple(
                review_sync,
                DAILY_DIR=str(root / "daily"),
                WEEKLY_DIR=str(root / "weekly"),
                MONTHLY_DIR=str(root / "monthly"),
                TODO_ARCHIVE_DIR=str(root / "archive"),
            ):
                weekly = review_sync.ensure_weekly_report("2026-10-14")
                monthly = review_sync.ensure_monthly_report("2026-10-14")
            self.assertTrue(Path(weekly).exists())
            self.assertTrue(Path(monthly).exists())

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
            fake_outbox = SyncOutbox(fake_store)
            with mock.patch.object(daily_todo_service.feishu_calendar, "calendar_mgr", calendar), \
                 mock.patch.object(idempotency, "store", fake_store), \
                 mock.patch.object(calendar_sync_service, "sync_outbox", fake_outbox):
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
