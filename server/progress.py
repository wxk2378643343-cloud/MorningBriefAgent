"""Progress-card lifecycle and controller independent from message orchestration."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Optional


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
        animation_thread.join(timeout=2.0)


class ProgressController:
    """Manages active thinking animations and cancellation handles keyed by request_id."""

    def __init__(self, update_fn: Optional[Callable[..., bool]] = None, logger=None):
        self._update_fn = update_fn
        self._logger = logger
        self._lock = threading.Lock()
        self._handles: dict[str, dict[str, Any]] = {}

    def set_update_fn(self, update_fn: Callable[..., bool]) -> None:
        self._update_fn = update_fn

    def start_progress(
        self,
        request_id: str,
        reply_message_id: str,
        update_fn: Optional[Callable[..., bool]] = None,
    ) -> threading.Event:
        """Start animation thread and register handle. Returns cancel_event."""
        update = update_fn or self._update_fn
        stop_event = threading.Event()
        cancel_event = threading.Event()

        thread = None
        if update and reply_message_id:
            thread = threading.Thread(
                target=animate,
                args=(reply_message_id, stop_event, update),
                kwargs={"logger": self._logger},
                name=f"Progress-{request_id[-8:]}",
                daemon=True,
            )
            thread.start()

        with self._lock:
            self._handles[request_id] = {
                "reply_message_id": reply_message_id,
                "stop_event": stop_event,
                "cancel_event": cancel_event,
                "thread": thread,
            }
        return cancel_event

    def get_cancel_event(self, request_id: str) -> Optional[threading.Event]:
        with self._lock:
            handle = self._handles.get(request_id)
            return handle["cancel_event"] if handle else None

    def stop_progress(
        self,
        request_id: str,
        *,
        terminal_text: Optional[str] = None,
        terminal_title: Optional[str] = None,
        template: Optional[str] = None,
    ) -> Optional[str]:
        """Stop animation thread, unregister, and optionally send a final card update.

        Returns reply_message_id.
        """
        with self._lock:
            handle = self._handles.pop(request_id, None)

        if not handle:
            return None

        reply_message_id = handle["reply_message_id"]
        stop_event = handle["stop_event"]
        thread = handle["thread"]

        # Signal stop to animation loop
        stop_event.set()
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

        # Optional terminal card update
        if terminal_text and self._update_fn and reply_message_id:
            try:
                self._update_fn(
                    reply_message_id,
                    terminal_text,
                    title=terminal_title or "🤖 AGY 智能协同助手",
                    template=template or "blue",
                )
            except Exception as exc:
                if self._logger:
                    self._logger.warning("Failed to update terminal progress card: %s", exc)

        return reply_message_id

    def cancel_progress(self, request_id: str, reason: str = "已撤回此条提问") -> None:
        """Trigger cancel event and update card to cancelled status."""
        with self._lock:
            handle = self._handles.get(request_id)
            if handle:
                handle["cancel_event"].set()

        self.stop_progress(
            request_id,
            terminal_text=f"🚫 **{reason}**\n\n该请求已停止处理，未产生后续操作。",
            terminal_title="🤖 AGY 智能协同助手 · 已取消",
            template="grey",
        )


progress_controller = ProgressController()
