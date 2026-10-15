"""Minimal OpenAI-compatible DeepSeek provider for offline-testable evaluation."""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeepSeekResponse:
    value: dict[str, Any] | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    duration_ms: int


class DeepSeekProvider:
    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = "https://api.deepseek.com/v1/chat/completions",
        model: str = "deepseek-chat",
        timeout: int = 45,
    ) -> None:
        if not api_key:
            raise ValueError("DeepSeek API key is required")
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout

    def ask_json(self, prompt: str) -> DeepSeekResponse:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "只返回合法 JSON，不要 Markdown 代码块。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        duration_ms = int((time.perf_counter() - started) * 1000)
        text = payload["choices"][0]["message"]["content"]
        try:
            value = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            value = None
        usage = payload.get("usage") or {}
        return DeepSeekResponse(
            value=value if isinstance(value, dict) else None,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            duration_ms=duration_ms,
        )
