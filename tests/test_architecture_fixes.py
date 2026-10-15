"""Regression tests for batching, provenance, freshness and partial failures."""

from __future__ import annotations

import datetime
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from core.agent import provider as agent_provider
from core.pipeline import AgentBatcher, OversizedBatchItem
from server import feishu_bot_server
from services.communications import chat_analysis, chat_renderer
from services.content import global_news, inspect_and_brief, news_sources
from services.planning import todo_candidates


class ArchitectureRegressionTests(unittest.TestCase):
    def test_agent_batcher_preserves_items_and_never_slices_json(self):
        items = [{"id": index, "text": "内容" * 40} for index in range(20)]
        batcher = AgentBatcher[dict](600)
        batches = batcher.partition(
            items, envelope=lambda values: {"items": values}
        )
        self.assertEqual(
            [item for batch in batches for item in batch],
            items,
        )
        self.assertTrue(all(
            len(json.dumps({"items": batch}, ensure_ascii=False)) <= 600
            for batch in batches
        ))
        with self.assertRaises(OversizedBatchItem):
            batcher.partition([{"text": "x" * 1000}])

    def test_news_quality_rejects_old_unknown_and_duplicate_items(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        recent = (now - datetime.timedelta(hours=2)).isoformat()
        old = (now - datetime.timedelta(days=10)).isoformat()
        news = {
            "domestic": [
                {"title": "同一新闻", "link": "https://a", "published": recent},
                {"title": "同一新闻", "link": "https://b", "published": recent},
                {"title": "旧闻", "link": "https://old", "published": old},
            ],
            "world": [
                {"title": "World", "link": "https://world", "published": recent},
            ],
        }
        tech = [
            {"name": "Release", "url": "https://tech", "published": recent},
            {"name": "Unknown", "url": "https://unknown", "published": ""},
        ]
        validated_news, validated_tech = global_news.validate_news_inputs(
            news, tech
        )
        quality = global_news.evaluate_news_quality(news, tech)
        self.assertEqual(len(validated_news["domestic"]), 1)
        self.assertEqual(len(validated_news["world"]), 1)
        self.assertEqual(len(validated_tech), 1)
        self.assertTrue(quality.ready)

    def test_news_renderer_is_pure_and_does_not_call_agent(self):
        recent = datetime.datetime.now(datetime.timezone.utc).isoformat()
        news = {
            "domestic": [{
                "title": "国内", "link": "https://d", "desc": "摘要",
                "published": recent,
            }],
            "world": [],
        }
        with mock.patch.object(agent_provider, "ask_json") as ask_json, \
             mock.patch.object(agent_provider, "ask_text") as ask_text:
            card = global_news.build_feishu_news_card(
                news, [], takeaway="已验证结论"
            )
        ask_json.assert_not_called()
        ask_text.assert_not_called()
        self.assertIn(
            "已验证结论",
            json.dumps(card, ensure_ascii=False),
        )

    def test_brief_rejects_untraceable_facts(self):
        data = {
            "documents": [{"path": "a.md", "excerpt": "明确事实"}],
            "emails": [],
        }
        response = {
            "facts": [
                {
                    "statement": "可回溯",
                    "source_id": "document:0",
                    "date_relevance": "近期",
                },
                {
                    "statement": "伪造",
                    "source_id": "document:99",
                    "date_relevance": "今日",
                },
            ],
            "priorities": [],
            "risks": [],
            "missing": [],
        }
        with mock.patch.object(agent_provider, "ask_json", return_value=response):
            facts = inspect_and_brief.analyze_brief_facts(data)
        self.assertEqual(
            [item["statement"] for item in facts["facts"]],
            ["可回溯"],
        )

    def test_chat_partial_failure_reports_actual_coverage(self):
        private = [{
            "name": "联系人",
            "total_count": 2,
            "my_count": 1,
            "friend_count": 1,
            "time_span": "09:00~10:00",
            "messages": [
                ("09:00", "本人", "第一条", "💬"),
                ("10:00", "对方", "第二条", "💬"),
            ],
        }]
        batches = [
            {"date": "2026-10-15", "private": [{
                "index": 0, "name": "联系人",
                "messages": [private[0]["messages"][0]],
            }], "groups": []},
            {"date": "2026-10-15", "private": [{
                "index": 0, "name": "联系人",
                "messages": [private[0]["messages"][1]],
            }], "groups": []},
        ]
        with mock.patch.object(
            chat_analysis, "_build_agent_batches", return_value=batches
        ), mock.patch.object(
            agent_provider,
            "ask_json",
            side_effect=[
                {"private": [], "groups": [], "overall": "第一批"},
                RuntimeError("failed"),
            ],
        ):
            result = chat_analysis.analyze_and_reflect(
                private, [], "2026-10-15"
            )
        card = chat_renderer.build_feishu_card(result, 0)
        rendered = json.dumps(card, ensure_ascii=False)
        self.assertEqual(result["planned_batches"], 2)
        self.assertEqual(result["successful_batches"], 1)
        self.assertEqual(result["failed_batches"], 1)
        self.assertEqual(result["analyzed_message_count"], 1)
        self.assertIn("Agent 覆盖不完整", rendered)

    def test_todo_candidates_do_not_require_keywords_or_stop_at_six(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "messages.db"
            timestamp = int(datetime.datetime.now().timestamp())
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE Msg_test("
                    "message_content TEXT, create_time INTEGER, status INTEGER)"
                )
                connection.executemany(
                    "INSERT INTO Msg_test VALUES (?, ?, ?)",
                    [
                        (f"普通表达内容第{index}条", timestamp + index, 1)
                        for index in range(12)
                    ],
                )
                connection.commit()
            values = todo_candidates.extract_candidates(
                sync_database=lambda: True,
                message_db=str(database),
                feishu_log="",
                todo_path="",
                keywords=("永远不匹配",),
                log_keywords=("永远不匹配",),
                limit=100,
            )
        self.assertEqual(len(values), 12)

    def test_bot_sends_fallback_error_when_progress_update_fails(self):
        with mock.patch.object(
            feishu_bot_server.daily_todo_service,
            "handle_todo_intent",
            return_value=None,
        ), mock.patch.object(
            feishu_bot_server, "get_and_clear_user_images", return_value=[]
        ), mock.patch.object(
            feishu_bot_server.feishu_archive,
            "archive_lifestyle_message",
            return_value=None,
        ), mock.patch.object(
            feishu_bot_server, "gather_agent_context", side_effect=RuntimeError("x")
        ), mock.patch.object(
            feishu_bot_server,
            "reply_feishu_message",
            side_effect=["om-progress", "om-error"],
        ) as reply, mock.patch.object(
            feishu_bot_server, "update_feishu_reply", return_value=False
        ):
            feishu_bot_server.process_message_async(
                "ou-user", "问题", "om-source"
            )
        self.assertEqual(reply.call_count, 2)
        self.assertIn("处理失败", reply.call_args_list[-1].kwargs["title"])


if __name__ == "__main__":
    unittest.main()
