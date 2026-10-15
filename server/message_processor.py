"""One-message use case, isolated from WebSocket transport and SDK callbacks."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any


def process_message(
    sender_open_id: str,
    user_text: str,
    msg_id: str,
    *,
    todo_handler: Callable[[str], str | None],
    get_images: Callable[[str], list[str]],
    archive_lifestyle: Callable[..., dict[str, Any] | None],
    reply: Callable[..., str | None],
    update: Callable[..., bool],
    gather_context: Callable[[str], str],
    ask_agent: Callable[[str, str, str], str],
    record_fact: Callable[..., str] | None = None,
    estimate_meal: Callable[..., Any] | None = None,
    animate: Callable[[str, threading.Event], None],
    stop_animation: Callable[..., None],
    event_fn: Callable[..., None],
    logger,
) -> None:
    progress_message_id = None
    animation_stop = None
    animation_thread = None
    try:
        event_fn(
            logger, "message_received",
            correlation_id=msg_id, message_id=msg_id,
        )
        todo_reply = todo_handler(user_text)
        if todo_reply:
            logger.info("todo_intent_matched message_id=%s", msg_id)
            reply(
                msg_id, todo_reply,
                title="📋 待办事项实时处理", template="indigo",
            )
            return

        attached_images = get_images(sender_open_id)
        archive_result = None
        try:
            archive_result = archive_lifestyle(
                user_text, msg_id, attached_images
            )
        except Exception as archive_error:
            logger.error(
                "lifestyle_archive_failed message_id=%s error=%s",
                msg_id, archive_error, exc_info=True,
            )
        if archive_result:
            logger.info(
                "lifestyle_archive_%s message_id=%s",
                "duplicate" if archive_result["duplicate"] else "succeeded",
                msg_id,
            )
        if attached_images:
            bullets = "\n".join(
                f"- file:///{path.replace(os.sep, '/')}"
                for path in attached_images
            )
            user_text = (
                f"{user_text}\n\n【用户发送的多模态图片附件】：\n{bullets}\n"
                "请使用可用的图片读取能力查看附件，并只根据图片真实细节回答。"
            )
        if archive_result:
            fact_id = None
            if record_fact:
                fact_id = record_fact(
                    message_id=msg_id,
                    category=archive_result["category"],
                    text=user_text,
                    image_paths=archive_result.get("image_paths", []),
                )
            if fact_id and estimate_meal:
                estimate_meal(
                    fact_id=fact_id,
                    category=archive_result["category"],
                    text=user_text,
                    image_paths=archive_result.get("image_paths", []),
                )
            user_text += (
                "\n\n【确定性本地归档状态】：已写入 Obsidian 的"
                f"“{archive_result['category']}”记录。"
                "请告知用户已归档，不要重复写入。"
            )

        progress_message_id = reply(
            msg_id,
            "⏳ **正在读取你的问题与已授权资料…**\n\n当前阶段：资料采集",
            title="🤖 AGY 智能协同助手 · 处理中",
            template="turquoise",
        )
        context = gather_context(user_text)
        if progress_message_id:
            update(
                progress_message_id,
                "**✦ · ·  Agent 正在深度分析**\n\n"
                "当前阶段：事实分析与回答生成\n\n"
                "请稍候，完成后本卡片会自动显示最终结果。",
                title="🤖 AGY 智能协同助手 · 思考中",
                template="turquoise",
            )
            animation_stop = threading.Event()
            animation_thread = threading.Thread(
                target=animate,
                args=(progress_message_id, animation_stop),
                name=f"ThinkingAnimation-{msg_id[-8:]}",
                daemon=True,
            )
            animation_thread.start()

        logger.info("agent_started message_id=%s", msg_id)
        reply_text = ask_agent(sender_open_id, user_text, context)
        stop_animation(animation_stop, animation_thread)
        animation_stop = None
        animation_thread = None
        updated = bool(progress_message_id) and update(
            progress_message_id,
            reply_text,
            title="🤖 AGY 智能协同助手",
            template="blue",
        )
        if not updated:
            reply(
                msg_id, reply_text,
                title="🤖 AGY 智能协同助手", template="blue",
            )
    except Exception as exc:
        logger.error(
            "message_processing_failed message_id=%s error=%s",
            msg_id, exc, exc_info=True,
        )
        stop_animation(animation_stop, animation_thread)
        error_text = (
            "❌ **本次处理未完成。**\n\n"
            "请稍后重试；错误详情已记录到本地日志。"
        )
        updated = bool(progress_message_id) and update(
            progress_message_id,
            error_text,
            title="🤖 AGY 智能协同助手 · 处理失败",
            template="red",
        )
        if not updated:
            reply(
                msg_id, error_text,
                title="🤖 AGY 智能协同助手 · 处理失败",
                template="red",
            )
