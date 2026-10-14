"""Feishu reply and media workflow for the WebSocket server."""

from __future__ import annotations

import datetime
import logging
import os
import re

from core.integrations.feishu.gateway import FeishuGateway

logger = logging.getLogger("AGYFeishuBot.Replies")


def download_feishu_image(
    gateway: FeishuGateway,
    image_dir: str,
    message_id: str,
    image_key: str,
) -> str | None:
    image_data = gateway.download_image(message_id, image_key)
    if not image_data:
        logger.error("Feishu image resource is empty")
        return None
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_key = re.sub(r"[^a-zA-Z0-9_-]", "_", image_key[-16:])
    filepath = os.path.join(image_dir, f"{timestamp}_{message_id[-8:]}_{safe_key}.jpg")
    try:
        with open(filepath, "wb") as handle:
            handle.write(image_data)
        logger.info("image_saved path=%s bytes=%s", filepath, len(image_data))
        return filepath
    except OSError as exc:
        logger.error("image_save_failed error=%s", exc)
        return None


def build_reply_card(
    content: str,
    title: str = "🤖 AGY 智能协同助手",
    template: str = "blue",
) -> dict:
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": [
            {"tag": "markdown", "content": content.strip()},
            {"tag": "hr"},
            {"tag": "note", "elements": [{
                "tag": "plain_text",
                "content": f"Google Antigravity 原生引擎 · 回复时戳 {now_str}",
            }]},
        ],
    }


def reply_feishu_message(
    gateway: FeishuGateway,
    message_id: str,
    reply_text: str,
    title: str = "🤖 AGY 智能协同助手",
    template: str = "blue",
) -> bool:
    card = build_reply_card(reply_text, title=title, template=template)
    if gateway.reply_card(message_id, card):
        logger.info("reply_card_succeeded message_id=%s", message_id)
        return True
    logger.warning("reply_card_failed fallback=text message_id=%s", message_id)
    if gateway.reply_text(message_id, reply_text):
        logger.info("reply_text_succeeded message_id=%s", message_id)
        return True
    logger.error("reply_failed message_id=%s", message_id)
    return False
