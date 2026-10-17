"""Editor- and vendor-neutral channel contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ChannelCapabilities:
    streaming: bool = False
    images: bool = False
    buttons: bool = False
    card_updates: bool = False
    proactive_messages: bool = True


@dataclass(frozen=True)
class ChannelMessage:
    text: str = ""
    markdown: str = ""
    attachments: tuple[dict[str, Any], ...] = ()
    actions: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(Protocol):
    name: str
    capabilities: ChannelCapabilities

    def send(self, destination: str, message: ChannelMessage) -> str: ...

    def update(self, message_id: str, message: ChannelMessage) -> bool: ...
