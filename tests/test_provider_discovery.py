import os
import unittest
from unittest.mock import patch

from core.agent.discovery import discovery_snapshot, discover_channels, discover_providers


class ProviderDiscoveryTests(unittest.TestCase):
    def test_discovery_never_returns_secret_values(self):
        with patch("core.agent.discovery.config.DEEPSEEK_API_KEY", "secret-value"), \
             patch("core.agent.discovery.config.DEEPSEEK_MODEL", "deepseek-chat"), \
             patch.dict(os.environ, {"AGY_PROCESS_RUNNING": "1"}, clear=False):
            snapshot = discovery_snapshot()
        rendered = repr(snapshot)
        self.assertNotIn("secret-value", rendered)
        deepseek = next(item for item in snapshot["providers"] if item["name"] == "deepseek")
        self.assertTrue(deepseek["configured"])
        self.assertEqual(deepseek["detail"], "model=deepseek-chat")

    def test_feishu_requires_both_credentials(self):
        with patch("core.agent.discovery.config.FEISHU_APP_ID", "app-id"), \
             patch("core.agent.discovery.config.FEISHU_APP_SECRET", ""):
            feishu = discover_channels()[0]
        self.assertFalse(feishu.available)
        self.assertFalse(feishu.configured)

    def test_local_agent_detection_is_explicit(self):
        with patch.dict(os.environ, {"AGY_PROCESS_RUNNING": "1"}, clear=False):
            providers = discover_providers()
        agy = next(item for item in providers if item.name == "agy")
        self.assertTrue(agy.available)


if __name__ == "__main__":
    unittest.main()
