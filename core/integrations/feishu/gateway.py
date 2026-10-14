"""Application-facing Feishu side-effect gateway."""

from __future__ import annotations

from typing import Any, Optional
from ..sync_outbox import sync_outbox

try:
    from . import calendar, client, idempotency
    from .task_gateway import task_gateway
except ImportError:
    from core.integrations.feishu import calendar, client, idempotency
    from core.integrations.feishu.task_gateway import task_gateway


class FeishuGateway:
    def __init__(self, client: Any = client.feishu_client):
        self.client = client

    def send_card_once(self, card: dict, key: str) -> bool:
        """Send a card once per stable business key.

        The local record is written only after the provider acknowledges
        success, so ordinary failed requests remain retryable.
        """
        attempt_owner = sync_outbox.begin(
            key,
            "feishu.card",
            {"idempotency_key": key, "card": card},
        )
        try:
            sent, _ = idempotency.store.execute_once(
                key,
                lambda: self.client.send_card(card),
                success=lambda result: result is True,
            )
            sync_outbox.finish(key, bool(sent), lease_owner=attempt_owner)
            return bool(sent)
        except Exception as exc:
            sync_outbox.finish(
                key,
                False,
                str(exc),
                lease_owner=attempt_owner,
            )
            raise

    def reply_card(self, message_id: str, card: dict) -> bool:
        return self.client.reply_message(message_id, card, "interactive")

    def reply_text(self, message_id: str, text: str) -> bool:
        return self.client.reply_message(message_id, {"text": text}, "text")

    def download_image(self, message_id: str, image_key: str):
        return self.client.download_image(message_id, image_key)

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
        return calendar.calendar_mgr.create_silent_event(**kwargs)


feishu_gateway = FeishuGateway()
