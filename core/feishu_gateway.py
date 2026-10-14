"""Application-facing Feishu side-effect gateway."""

from __future__ import annotations

from typing import Any, Optional

try:
    from . import feishu_calendar, feishu_client, idempotency
    from .feishu_task_gateway import task_gateway
except ImportError:
    import feishu_calendar
    import feishu_client
    import idempotency
    from feishu_task_gateway import task_gateway


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

    # Task and calendar operations intentionally stay behind this facade so
    # services do not know which provider adapter implements them.
    def list_tasks(self, page_size: int = 50) -> list[dict[str, Any]]:
        return task_gateway.list(page_size)

    def create_task(self, summary: str, description: str = "",
                    due_timestamp: Optional[int] = None) -> Optional[dict]:
        return task_gateway.create(summary, description, due_timestamp)

    def complete_task(self, task_id: str) -> bool:
        return task_gateway.complete(task_id)

    def delete_task(self, task_id: str) -> bool:
        return task_gateway.delete(task_id)

    def create_calendar_event(self, **kwargs):
        return feishu_calendar.calendar_mgr.create_silent_event(**kwargs)


feishu_gateway = FeishuGateway()
