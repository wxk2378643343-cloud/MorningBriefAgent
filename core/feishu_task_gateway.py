"""Feishu Task API adapter.

Business services depend on this narrow gateway instead of constructing
provider URLs and authentication payloads themselves.
"""

from __future__ import annotations

from typing import Any, Optional

import requests

try:
    from . import config
except ImportError:
    import config


class FeishuTaskGateway:
    BASE = "https://open.feishu.cn/open-apis"

    def __init__(self, session: Any = requests):
        self.session = session

    def _token(self) -> Optional[str]:
        response = self.session.post(
            f"{self.BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": config.FEISHU_APP_ID, "app_secret": config.FEISHU_APP_SECRET},
            timeout=10,
        )
        return response.json().get("tenant_access_token")

    def list(self, page_size: int = 50) -> list[dict[str, Any]]:
        for _ in range(3):
            try:
                token = self._token()
                if not token:
                    continue
                response = self.session.get(
                    f"{self.BASE}/task/v1/tasks?user_id_type=open_id&page_size={page_size}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                payload = response.json()
                if payload.get("code") == 0:
                    return payload.get("data", {}).get("items", [])
            except Exception:
                continue
        return []

    def create(
        self,
        summary: str,
        description: str = "",
        due_timestamp: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        token = self._token()
        if not token:
            return None
        payload: dict[str, Any] = {
            "summary": summary,
            "description": description or "由 AGY 智能体自动创建并同步",
            "members": [{"id": config.FEISHU_USER_OPEN_ID, "type": "user", "role": "assignee"}],
        }
        if due_timestamp:
            payload["due"] = {"timestamp": str(due_timestamp)}
        response = self.session.post(
            f"{self.BASE}/task/v2/tasks?user_id_type=open_id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
            timeout=10,
        )
        result = response.json()
        return result.get("data", {}).get("task") if result.get("code") == 0 else None

    def complete(self, task_id: str) -> bool:
        token = self._token()
        if not token:
            return False
        response = self.session.post(
            f"{self.BASE}/task/v1/tasks/{task_id}/complete",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=10,
        )
        return response.json().get("code") == 0

    def delete(self, task_id: str) -> bool:
        token = self._token()
        if not token:
            return False
        response = self.session.delete(
            f"{self.BASE}/task/v1/tasks/{task_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        return response.json().get("code") == 0


task_gateway = FeishuTaskGateway()
