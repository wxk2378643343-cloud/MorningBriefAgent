"""Stable provider contract shared by workflows and provider adapters."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol


@dataclass(frozen=True)
class ProviderCapabilities:
    streaming: bool = False
    images: bool = False
    tools: bool = False
    subtasks: bool = False
    structured_output: bool = True
    cancellation: bool = True


@dataclass(frozen=True)
class AgentRequest:
    task: str
    prompt: str
    context: str = ""
    timeout_seconds: float = 60
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentResponse:
    provider: str
    model: str
    text: str
    structured: dict[str, Any] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    status: str
    detail: str = ""


class AgentProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    def invoke(
        self,
        request_id: str,
        request: AgentRequest,
        cancel_event: threading.Event | None = None,
    ) -> AgentResponse: ...

    def stream(self, request_id: str, request: AgentRequest) -> Iterable[str]: ...

    def cancel(self, request_id: str) -> bool: ...

    def health(self) -> ProviderHealth: ...


class ProviderError(RuntimeError):
    """Classified provider failure that workflows can handle consistently."""

    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
