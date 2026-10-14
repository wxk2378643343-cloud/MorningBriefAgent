"""Application-facing Feishu side-effect gateway."""

from __future__ import annotations

from typing import Any, Optional

try:
    from . import feishu_client, idempotency
except ImportError:
    import feishu_client
    import idempotency


class FeishuGateway:
    def __init__(self, client: Any = feishu_client.feishu_client):
        self.client = client

    def send_card_once(self, card: dict, key: str) -> bool:
        """Send a card once per stable business key.

        The local record is written only after the provider acknowledges
        success, so ordinary failed requests remain retryable.
        """
        if idempotency.store.get(key):
            return True
        sent = self.client.send_card(card)
        if sent:
            idempotency.store.put(key, {"provider": "feishu", "sent": True})
        return sent


feishu_gateway = FeishuGateway()
