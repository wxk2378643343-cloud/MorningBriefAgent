"""Service orchestrating agent requests, state machine transitions, and provider boundary."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

from core.agent.agy_adapter import AgyProviderAdapter
from core.agent.runtime import AgentProvider, AgentRequest, AgentResponse, ProviderError
from server.progress import progress_controller
from storage import agent_requests as request_repo

logger = logging.getLogger(__name__)


class AgentRequestService:
    def __init__(
        self,
        provider: Optional[AgentProvider] = None,
        database_path: Optional[str] = None,
    ):
        self._provider = provider or AgyProviderAdapter()
        self._database_path = database_path

    def set_provider(self, provider: AgentProvider) -> None:
        self._provider = provider

    def create_request(
        self,
        *,
        source_message_id: str,
        prompt: str,
        context: str = "",
        request_kind: str = "conversation",
    ) -> tuple[str, bool]:
        """Idempotently register an agent request."""
        return request_repo.create_agent_request(
            source_message_id=source_message_id,
            prompt=prompt,
            context=context,
            request_kind=request_kind,
            provider=getattr(self._provider, "name", "agy"),
            database_path=self._database_path,
        )

    def attach_reply_card(self, request_id: str, reply_message_id: str) -> bool:
        return request_repo.attach_reply_message_id(
            request_id, reply_message_id, database_path=self._database_path
        )

    def execute_request(
        self,
        request_id: str,
        *,
        task: str = "feishu-conversation",
        cancel_event: Optional[threading.Event] = None,
    ) -> tuple[str, bool]:
        """Execute request through provider with atomic state machine checks.

        Returns:
            (result_or_error_text, success_bool)
        """
        req_data = request_repo.get_agent_request(request_id, database_path=self._database_path)
        if not req_data:
            return "❌ 未找到对应请求记录", False

        # Atomic transition to running
        if not request_repo.mark_request_running(request_id, database_path=self._database_path):
            current_status = req_data.get("status")
            logger.info(
                "Request %s could not transition to running (current status: %s)",
                request_id, current_status
            )
            return f"❌ 请求当前处于不可执行状态: {current_status}", False

        # Build request object
        req_obj = AgentRequest(
            task=task,
            prompt=req_data["prompt"],
            context=req_data.get("context") or "",
        )

        try:
            response = self._provider.invoke(
                request_id, req_obj, cancel_event=cancel_event
            )
            reply_text = response.text

            # Atomic transition to completed:
            # If request was cancelled in SQLite while provider was running,
            # mark_request_completed returns False and we MUST DROP the result!
            if request_repo.mark_request_completed(request_id, reply_text, database_path=self._database_path):
                return reply_text, True
            else:
                logger.warning(
                    "Request %s was cancelled during execution; dropping provider response.",
                    request_id,
                )
                return "🚫 请求已在执行期间被撤回或取消。", False

        except ProviderError as p_err:
            error_msg = str(p_err)
            request_repo.mark_request_failed(request_id, error_msg, database_path=self._database_path)
            return f"❌ Agent 响应异常: {error_msg}", False

        except Exception as exc:
            error_msg = f"unexpected_error: {exc}"
            request_repo.mark_request_failed(request_id, error_msg, database_path=self._database_path)
            return f"❌ 系统执行异常: {exc}", False

    def cancel_by_source_message(self, source_message_id: str) -> list[str]:
        """Cancel requests associated with a source message and stop animations."""
        cancelled_ids = request_repo.cancel_by_source_message(
            source_message_id, database_path=self._database_path
        )
        for req_id in cancelled_ids:
            # Tell provider to cancel
            try:
                self._provider.cancel(req_id)
            except Exception as exc:
                logger.warning("Provider cancel failed for %s: %exc", req_id, exc)

            # Signal progress controller to stop and update card
            progress_controller.cancel_progress(req_id, reason="用户已撤回此条提问")
        return cancelled_ids

    def recover_interrupted_requests(self) -> int:
        """Startup cleanup: move dangling running requests to interrupted."""
        return request_repo.recover_interrupted_requests(database_path=self._database_path)


agent_request_service = AgentRequestService()
