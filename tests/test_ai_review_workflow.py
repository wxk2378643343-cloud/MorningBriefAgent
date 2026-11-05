"""Offline regression tests for the two-level DeepSeek review publisher."""

import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "ai-review.yml"
SCRIPT_PATH = PROJECT_ROOT / ".github" / "scripts" / "ai_review.py"

SPEC = importlib.util.spec_from_file_location("ai_review", SCRIPT_PATH)
ai_review = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = ai_review
SPEC.loader.exec_module(ai_review)


class AiReviewWorkflowTests(unittest.TestCase):
    def test_workflow_uses_repository_publisher_with_minimal_permissions(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("pull-requests: write", workflow)
        self.assertNotIn("write-all", workflow)
        self.assertIn("python .github/scripts/ai_review.py", workflow)
        self.assertNotIn("anc95/ChatGPT-CodeReview", workflow)
        self.assertNotIn("continue-on-error:", workflow)

    def test_changed_lines_returns_only_real_new_lines(self):
        patch = (
            "@@ -10,3 +10,4 @@\n"
            " context\n"
            "-old\n"
            "+new\n"
            "+extra\n"
            " tail\n"
        )
        self.assertEqual(ai_review.changed_lines(patch), frozenset({11, 12}))

    def test_select_files_limits_scope_and_patch_size(self):
        files = [
            {
                "filename": "services/planning.py",
                "status": "modified",
                "patch": "@@ -1 +1 @@\n-old\n+new",
            },
            {
                "filename": "docs/guide.md",
                "status": "modified",
                "patch": "@@ -1 +1 @@\n-old\n+new",
            },
            {
                "filename": "core/huge.py",
                "status": "modified",
                "patch": "x" * (ai_review.MAX_PATCH_LENGTH + 1),
            },
        ]
        selected = ai_review.select_files(files)
        self.assertEqual([item.path for item in selected], ["services/planning.py"])

    def test_review_has_summary_and_one_comment_per_valid_finding(self):
        files = [
            ai_review.ChangedFile(
                "services/planning.py",
                "@@ -10,1 +10,2 @@\n old\n+new",
                frozenset({11}),
            )
        ]
        result = {
            "summary": {
                "verdict": "修复后合并",
                "overview": "总体评价。",
                "strengths": ["边界清晰"],
                "risks": ["缺少校验"],
                "test_assessment": "需要失败路径测试。",
            },
            "findings": [
                {
                    "path": "services/planning.py",
                    "line": 11,
                    "severity": "P1",
                    "title": "状态未校验",
                    "trigger": "提交非法状态",
                    "impact": "污染业务事实",
                    "test_gap": "只有成功路径",
                    "fix": "服务层校验并增加失败测试",
                },
                {
                    "path": "services/planning.py",
                    "line": 99,
                    "severity": "P2",
                    "title": "错误定位",
                },
            ],
        }

        body, comments = ai_review.prepare_review(result, files)

        self.assertIn("## DeepSeek 关键代码评审", body)
        self.assertIn("**结论：修复后合并**", body)
        self.assertIn("未发布为行内评论的问题", body)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["path"], "services/planning.py")
        self.assertEqual(comments[0]["line"], 11)
        self.assertIn("[P1] 状态未校验", comments[0]["body"])

    def test_model_result_accepts_fenced_json(self):
        result = ai_review.parse_model_result(
            '```json\n{"summary":{"verdict":"建议合并"},"findings":[]}\n```'
        )
        self.assertEqual(result["summary"]["verdict"], "建议合并")


if __name__ == "__main__":
    unittest.main()
