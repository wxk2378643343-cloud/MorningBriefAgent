"""Progress-card lifecycle independent from message orchestration."""

from __future__ import annotations

import threading
from collections.abc import Callable


THINKING_FRAMES = ("✦ · ·", "· ✦ ·", "· · ✦", "· ✦ ·")
THINKING_FRAME_SECONDS = 0.8


def animate(
    reply_message_id: str,
    stop_event: threading.Event,
    update: Callable[..., bool],
    *,
    logger=None,
) -> None:
    frame_index = 0
    while not stop_event.wait(THINKING_FRAME_SECONDS):
        frame = THINKING_FRAMES[frame_index % len(THINKING_FRAMES)]
        frame_index += 1
        if not update(
            reply_message_id,
            f"**{frame}  Agent 正在深度分析**\n\n"
            "当前阶段：事实分析与回答生成\n\n"
            "请稍候，完成后本卡片会自动显示最终结果。",
            title="🤖 AGY 智能协同助手 · 思考中",
            template="turquoise",
        ):
            if logger:
                logger.warning(
                    "thinking_animation_stopped update_failed message_id=%s",
                    reply_message_id,
                )
            return


def stop(
    stop_event: threading.Event | None,
    animation_thread: threading.Thread | None,
) -> None:
    if stop_event:
        stop_event.set()
    if animation_thread and animation_thread.is_alive():
        animation_thread.join(timeout=20)
