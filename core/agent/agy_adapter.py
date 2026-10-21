"""Adapter implementing AgentProvider for Google Antigravity (language_server.exe agentapi).

All AGY-specific process details, ports, tokens, and transcript monitoring
are encapsulated strictly within this adapter.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Iterable

from core.agent.runtime import (
    AgentProvider,
    AgentRequest,
    AgentResponse,
    ProviderCapabilities,
    ProviderError,
    ProviderHealth,
)
from storage.usage import UsageTimer, estimate_tokens, record_usage

try:
    from . import agy_bridge
except ImportError:
    from core.agent import agy_bridge


class AgyProviderAdapter:
    name = "agy"
    capabilities = ProviderCapabilities(
        streaming=False,
        images=True,
        tools=True,
        subtasks=True,
        structured_output=True,
        cancellation=True,
    )

    def invoke(
        self,
        request_id: str,
        request: AgentRequest,
        cancel_event: threading.Event | None = None,
    ) -> AgentResponse:
        timer = UsageTimer()

        if cancel_event and cancel_event.is_set():
            raise ProviderError("request_cancelled")

        # Execute via existing bridge
        try:
            result_text = agy_bridge.ask_native_agy(
                request.task,
                request.prompt,
                request.context,
            )
        except Exception as exc:
            raise ProviderError(f"agy_bridge_exception: {exc}") from exc

        if cancel_event and cancel_event.is_set():
            raise ProviderError("request_cancelled")

        if not result_text or result_text.startswith("❌"):
            # Classified provider errors (e.g. 503, timeout, offline)
            raise ProviderError(result_text or "agy_empty_response")

        input_tok = estimate_tokens(request.prompt + request.context)
        output_tok = estimate_tokens(result_text)
        duration = timer.elapsed_ms()

        record_usage(
            task=request.task,
            provider="agy",
            input_tokens=input_tok,
            output_tokens=output_tok,
            duration_ms=duration,
            status="success",
        )

        return AgentResponse(
            provider="agy",
            model="antigravity",
            text=result_text,
            structured=None,
            input_tokens=input_tok,
            output_tokens=output_tok,
            duration_ms=duration,
        )

    def stream(self, request_id: str, request: AgentRequest) -> Iterable[str]:
        # AGY adapter returns batch text currently
        resp = self.invoke(request_id, request)
        yield resp.text

    def cancel(self, request_id: str) -> bool:
        # AGY is best-effort cancel; upper service drops outputs immediately
        return True

    def health(self) -> ProviderHealth:
        port, token = agy_bridge.detect_agy_process()
        if port and token:
            return ProviderHealth(available=True, status="ready", detail=f"Port: {port}")
        return ProviderHealth(available=False, status="offline", detail="AGY language_server not detected")
