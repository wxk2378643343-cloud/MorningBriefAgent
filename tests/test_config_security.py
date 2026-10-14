"""Offline security and configuration tests."""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
from core.runtime import config
from core.agent import provider as agent_provider
from services.planning import review_sync as review_sync_service


class ConfigSecurityTests(unittest.TestCase):
    def test_agent_provider_parses_fenced_json(self):
        with mock.patch.object(
            agent_provider.agy_bridge,
            "ask_native_agy",
            return_value="```json\n{\"todos\": [\"review\"]}\n```",
        ):
            result = agent_provider.ask_json("test", "return json")
        self.assertEqual(result, {"todos": ["review"]})

    def test_agent_provider_rejects_non_object_json(self):
        with mock.patch.object(
            agent_provider.agy_bridge,
            "ask_native_agy",
            return_value='["not an object"]',
        ):
            self.assertIsNone(agent_provider.ask_json("test", "return json"))

    def test_env_loader_does_not_override_process_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "MBA_TEST_EXISTING=from-file\nMBA_TEST_NEW='loaded value'\n",
                encoding="utf-8",
            )
            os.environ["MBA_TEST_EXISTING"] = "from-process"
            os.environ.pop("MBA_TEST_NEW", None)
            try:
                config.load_env_file(env_file)
                self.assertEqual(os.environ["MBA_TEST_EXISTING"], "from-process")
                self.assertEqual(os.environ["MBA_TEST_NEW"], "loaded value")
            finally:
                os.environ.pop("MBA_TEST_EXISTING", None)
                os.environ.pop("MBA_TEST_NEW", None)

    def test_public_example_contains_placeholders_only(self):
        content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("FEISHU_APP_SECRET=your_feishu_app_secret_here", content)
        self.assertNotRegex(content, r"FEISHU_APP_SECRET=(?!your_)[^\r\n]+")

    def test_source_has_no_feishu_secret_default(self):
        content = (PROJECT_ROOT / "core" / "runtime" / "config.py").read_text(encoding="utf-8")
        self.assertNotRegex(
            content,
            r'FEISHU_APP_SECRET\s*=\s*os\.getenv\([^,]+,\s*"[^"]+"\)',
        )

    def test_core_package_imports_cleanly(self):
        import core

        self.assertTrue(hasattr(core, "feishu_client"))
        self.assertTrue(hasattr(core, "get_latest_high_value_email_digest"))

    def test_gitignore_covers_private_runtime_files(self):
        content = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        for rule in (
            ".env",
            "!.env.example",
            "logs/",
            "data/*.json",
            "received_images/*",
            "__pycache__/",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, content)

    def test_public_files_do_not_contain_common_live_feishu_ids(self):
        patterns = (
            re.compile(r"\bcli_[a-zA-Z0-9]{12,}\b"),
            re.compile(r"\bou_[a-zA-Z0-9]{12,}\b"),
            re.compile(r"\boc_[a-zA-Z0-9]{12,}\b"),
        )
        files = [
            *PROJECT_ROOT.glob("*.py"),
            *PROJECT_ROOT.glob("*.md"),
            *PROJECT_ROOT.glob("*.example"),
            *PROJECT_ROOT.glob("core/*.py"),
            *PROJECT_ROOT.glob("server/*.py"),
            *PROJECT_ROOT.glob("services/*.py"),
            *PROJECT_ROOT.glob("tests/*.py"),
        ]
        for path in files:
            text = path.read_text(encoding="utf-8-sig")
            for pattern in patterns:
                with self.subTest(path=path, pattern=pattern.pattern):
                    self.assertIsNone(pattern.search(text))

    def test_markdown_section_update_preserves_later_content(self):
        original = (
            "# 日记\n\n"
            "## 待办\n\n- [ ] 旧事项\n\n"
            "---\n\n"
            "## 手写复盘\n\n这段内容不能丢。\n"
        )
        updated = review_sync_service.replace_markdown_section(
            original,
            "## 待办",
            "- [x] 新事项",
        )
        self.assertIn("- [x] 新事项", updated)
        self.assertNotIn("旧事项", updated)
        self.assertIn("## 手写复盘\n\n这段内容不能丢。", updated)

    def test_daily_sync_does_not_delete_handwritten_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = root / "daily"
            weekly = root / "weekly"
            monthly = root / "monthly"
            archive = root / "archive"
            daily.mkdir()
            journal = daily / "2026-10-14.md"
            journal.write_text(
                "# 日记\n\n"
                "## 📋 二、今日核心待办执行闭环\n\n"
                "- [x] **保留事项**\n\n"
                "---\n\n"
                "## 手写复盘\n\n不要覆盖这段文字。\n",
                encoding="utf-8",
            )
            with mock.patch.multiple(
                review_sync_service,
                DAILY_DIR=str(daily),
                WEEKLY_DIR=str(weekly),
                MONTHLY_DIR=str(monthly),
                TODO_ARCHIVE_DIR=str(archive),
            ):
                review_sync_service.ensure_daily_journal(
                    "2026-10-14",
                    ["保留事项", "新增事项"],
                )
            updated = journal.read_text(encoding="utf-8")
            self.assertIn("- [x] **保留事项**", updated)
            self.assertIn("- [ ] **新增事项**", updated)
            self.assertIn("## 手写复盘\n\n不要覆盖这段文字。", updated)


if __name__ == "__main__":
    unittest.main()
