"""Tests for the OpenAI-compatible DeepSeek adapter."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from core.agent.deepseek_provider import DeepSeekProvider


class DeepSeekProviderTests(unittest.TestCase):
    def test_parses_json_and_preserves_provider_usage(self):
        payload = {
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 5,
                "total_tokens": 16,
            },
        }
        response = mock.Mock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__ = lambda self: self
        response.__exit__ = mock.Mock(return_value=False)
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch(
            "core.agent.deepseek_provider.urllib.request.build_opener",
            return_value=opener,
        ):
            result = DeepSeekProvider("secret").ask_json("return json")
        self.assertEqual(result.value, {"ok": True})
        self.assertEqual(result.total_tokens, 16)
        self.assertEqual(opener.open.call_args.args[0].full_url,
                         "https://api.deepseek.com/v1/chat/completions")

    def test_requires_key(self):
        with self.assertRaises(ValueError):
            DeepSeekProvider("")
