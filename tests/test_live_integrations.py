"""Opt-in read-only integration checks.

Run explicitly with RUN_LIVE_INTEGRATION=1. These tests never create tasks,
calendar events, or messages; they only verify provider authentication/listing.
"""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

import config
from feishu_task_gateway import FeishuTaskGateway


@unittest.skipUnless(
    os.getenv("RUN_LIVE_INTEGRATION") == "1",
    "set RUN_LIVE_INTEGRATION=1 to run read-only provider checks",
)
class LiveIntegrationTests(unittest.TestCase):
    def test_feishu_task_read_access(self):
        if not config.FEISHU_APP_ID or not config.FEISHU_APP_SECRET:
            self.skipTest("Feishu credentials are not configured")
        tasks = FeishuTaskGateway().list(page_size=1)
        self.assertIsInstance(tasks, list)


if __name__ == "__main__":
    unittest.main()
