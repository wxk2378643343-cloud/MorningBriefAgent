"""Offline regression tests for the DeepSeek pull-request review workflow."""

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "ai-review.yml"


class AiReviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_uses_safe_event_and_minimal_permissions(self):
        self.assertRegex(self.workflow, r"(?m)^  pull_request:\s*$")
        self.assertNotRegex(self.workflow, r"(?m)^  pull_request_target:\s*$")
        self.assertIn(
            "github.event.pull_request.head.repo.full_name == github.repository",
            self.workflow,
        )
        self.assertIn("github.event.pull_request.draft == false", self.workflow)
        self.assertIn("github.actor != 'dependabot[bot]'", self.workflow)
        self.assertRegex(self.workflow, r"actions/checkout@[0-9a-f]{40}")
        self.assertRegex(
            self.workflow,
            r"anc95/ChatGPT-CodeReview@[0-9a-f]{40}",
        )
        self.assertIn("persist-credentials: false", self.workflow)

    def test_limits_reviews_to_critical_code(self):
        for pattern in (
            '"core/**"',
            '"services/**"',
            '"storage/**"',
            '"server/**"',
            '"desktop/src/**"',
            '"desktop/src-tauri/**"',
            '".github/workflows/**"',
        ):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, self.workflow)
        self.assertIn("INCLUDE_PATTERNS:", self.workflow)
        self.assertIn("IGNORE_PATTERNS:", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s+IGNORE_PATTERN:")
        self.assertIn("MAX_PATCH_LENGTH:", self.workflow)

    def test_configuration_or_provider_failure_is_visible(self):
        self.assertNotIn("continue-on-error:", self.workflow)
        self.assertIn("Validate AI review configuration", self.workflow)
        self.assertIn('[[ -z "$AI_API_KEY" ]]', self.workflow)
        self.assertIn("exit 1", self.workflow)

    def test_prompt_requires_evidence_and_project_rules(self):
        for requirement in (
            "精确文件与变更行",
            "可复现的触发路径或输入",
            "SQLite 是结构化业务事实的唯一来源",
            "非法输入返回稳定 4xx",
            "排他性结束边界",
            "前端必须检查 response.ok",
            "Gateway、幂等和 Outbox",
            "需人工核验",
            "未发现需要阻止合并的问题",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, self.workflow)


if __name__ == "__main__":
    unittest.main()
