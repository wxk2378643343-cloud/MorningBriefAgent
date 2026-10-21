"""One-message use case, isolated from WebSocket transport and SDK callbacks."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any
from services.agent_requests import agent_request_service
from server.progress import progress_controller

from storage.usage import clear_last_usage, get_last_usage


def _append_usage_footer(reply_text: str) -> str:
    usage = get_last_usage()
    if not usage or not isinstance(reply_text, str):
        return reply_text
    source = "估算" if usage.get("token_source") == "estimated" else "实际"
    return (
        f"{reply_text.rstrip()}\n\n"
        f"<sub>Token：{source}输入 {usage.get('input_tokens') or 0} · "
        f"输出 {usage.get('output_tokens') or 0} · "
        f"合计 {usage.get('total_tokens') or 0} · "
        f"{usage.get('provider', 'unknown')}</sub>"
    )


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
    confirm_lifestyle: Callable[..., str | None] | None = None,
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
        if confirm_lifestyle:
            confirmation = confirm_lifestyle(user_text, actor=sender_open_id)
            if confirmation:
                reply(
                    msg_id, confirmation,
                    title="🥗 饮食记录确认", template="green",
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
        estimate_result = None
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
                estimate_result = estimate_meal(
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
        # 1. Idempotently register agent request in SQLite
        request_id, is_new = agent_request_service.create_request(
            source_message_id=msg_id,
            prompt=user_text,
            context=context,
            request_kind="conversation",
        )
        if not is_new:
            logger.info("Duplicate message %s skipped; request %s already exists", msg_id, request_id)
            return

        if progress_message_id:
            agent_request_service.attach_reply_card(request_id, progress_message_id)
            update(
                progress_message_id,
                "**✦ · ·  Agent 正在深度分析**\n\n"
                "当前阶段：事实分析与回答生成\n\n"
                "请稍候，完成后本卡片会自动显示最终结果。",
                title="🤖 AGY 智能协同助手 · 思考中",
                template="turquoise",
            )
            progress_controller.set_update_fn(update)
            cancel_event = progress_controller.start_progress(request_id, progress_message_id, update)
        else:
            cancel_event = None

        logger.info("agent_started message_id=%s request_id=%s", msg_id, request_id)
        clear_last_usage()

        # 2. Execute via AgentRequestService
        raw_reply, ok = agent_request_service.execute_request(
            request_id, cancel_event=cancel_event
        )

        if not ok:
            progress_controller.stop_progress(
                request_id,
                terminal_text=f"❌ **本次处理未完成。**\n\n{raw_reply}",
                terminal_title="🤖 AGY 智能协同助手 · 处理失败",
                template="red",
            )
            return

        # 3. Success: format reply text and update terminal card
        reply_text = _append_usage_footer(raw_reply)
        if estimate_result and estimate_result.get("status") == "pending":
            calories = estimate_result.get("calories_estimated")
            protein = estimate_result.get("protein_estimated")
            calories_text = (
                f"{calories:g}" if isinstance(calories, (int, float))
                else "未能估算"
            )
            reply_text = (
                f"🥗 **本次餐食已记录**：约 {calories_text} kcal"
                + (f"，蛋白质约 {protein:g} g" if protein is not None else "")
                + "。\n\n"
                + "这是 Agent 根据当前输入生成的估算值；如果不准确，直接告诉我正确热量，我会修改原记录。\n\n"
                + reply_text
            )

        progress_controller.stop_progress(
            request_id,
            terminal_text=reply_text,
            terminal_title="🤖 AGY 智能协同助手",
            template="blue",
        )
        if progress_message_id:
            reply(
                msg_id,
                "✅ 已完成，请查看上一条结果。",
                title="🤖 AGY 智能协同助手 · 已完成",
                template="green",
            )
        else:
            reply(msg_id, reply_text, title="🤖 AGY 智能协同助手", template="blue")
    except Exception as exc:
        logger.error(
            "message_processing_failed message_id=%s error=%s",
            msg_id, exc, exc_info=True,
        )
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
