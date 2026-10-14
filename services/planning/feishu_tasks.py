"""Application service for Feishu task operations."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from core.integrations.feishu import idempotency
from core.integrations.feishu.gateway import feishu_gateway
from core.integrations.sync_outbox import sync_outbox
from core.runtime import config
from . import review_sync as review_sync_service


def delete_feishu_task(task_id: str, gateway=None) -> bool:
    """Delete a Feishu task by ID."""
    try:
        return (gateway or feishu_gateway).delete_task(task_id)
    except Exception as exc:
        print(f"⚠️ 删除飞书任务异常: {exc}")
        return False


def list_feishu_tasks(page_size: int = 50, gateway=None) -> List[Dict[str, Any]]:
    """Fetch recent Feishu tasks with auto-retry."""
    try:
        return (gateway or feishu_gateway).list_tasks(page_size)
    except Exception as exc:
        print(f"⚠️ 获取飞书任务列表网络异常: {exc}")
        return []


def create_feishu_task(
    summary: str,
    description: str = "",
    due_timestamp: Optional[int] = None,
    check_duplicate: bool = True,
    idempotency_key: str = "",
    gateway=None,
    record_outbox: bool = True,
) -> Optional[dict]:
    """Create a task with local idempotency and provider-side duplicate guard."""
    summary = summary.strip()
    if not summary:
        return None

    if idempotency_key:
        saved = idempotency.store.get(idempotency_key)
        if saved and saved.get("status") == "succeeded":
            result = saved.get("result")
            if isinstance(result, dict):
                result = dict(result)
                result["reused"] = True
            return result
        if saved and saved.get("provider_id"):
            return {
                "id": saved["provider_id"],
                "task_id": saved["provider_id"],
                "summary": summary,
                "reused": True,
            }

    if check_duplicate:
        try:
            for task in list_feishu_tasks(page_size=50, gateway=gateway):
                if (
                    task.get("complete_time") == "0"
                    and task.get("summary", "").strip() == summary
                ):
                    provider_id = task.get("id")
                    result = {
                        "task_id": provider_id,
                        "id": provider_id,
                        "summary": summary,
                        "reused": True,
                    }
                    if idempotency_key and provider_id:
                        idempotency.store.put(
                            idempotency_key,
                            {"status": "succeeded", "result": result},
                        )
                    return result
        except Exception:
            # The duplicate guard is best effort; the idempotency store remains
            # the authoritative local protection.
            pass

    try:
        attempt_owner = None
        if idempotency_key:
            if record_outbox:
                attempt_owner = sync_outbox.begin(
                    idempotency_key,
                    "feishu.task",
                    {
                        "idempotency_key": idempotency_key,
                        "summary": summary,
                        "description": description,
                        "due_timestamp": due_timestamp,
                    },
                )
            task_data, reused = idempotency.store.execute_once(
                idempotency_key,
                    lambda: (gateway or feishu_gateway).create_task(
                    summary, description, due_timestamp
                ),
                success=lambda result: bool(result),
            )
            if isinstance(task_data, dict) and reused:
                task_data = dict(task_data)
                task_data["reused"] = True
            if record_outbox:
                sync_outbox.finish(
                    idempotency_key,
                    bool(task_data),
                    lease_owner=attempt_owner,
                )
        else:
            task_data = (gateway or feishu_gateway).create_task(
                summary, description, due_timestamp
            )
        return task_data or None
    except Exception as exc:
        if idempotency_key and record_outbox:
            sync_outbox.finish(
                idempotency_key,
                False,
                str(exc),
                lease_owner=attempt_owner,
            )
        print(f"⚠️ 创建飞书任务网络异常: {exc}")
        return None


def complete_feishu_task(task_id: str, gateway=None) -> bool:
    """Mark an official Feishu task as completed."""
    try:
        if (gateway or feishu_gateway).complete_task(task_id):
            print(f"✅ 成功将飞书任务标记为完成: {task_id}")
            return True
        print(f"⚠️ 标记飞书任务完成失败 ({task_id})")
        return False
    except Exception as exc:
        print(f"⚠️ 标记飞书任务完成网络异常: {exc}")
        return False


def complete_task_by_keyword(keyword: str, gateway=None) -> Optional[str]:
    """Complete matching Feishu tasks and sync local checkmarks."""
    kw = keyword.strip()
    if not kw:
        return None

    completed_names = []
    for task in list_feishu_tasks(gateway=gateway):
        summary = task.get("summary", "")
        task_id = task.get("id", "")
        if kw in summary or summary in kw:
            if complete_feishu_task(task_id, gateway=gateway):
                completed_names.append(summary)

    if config.TODAY_TODO_PATH and os.path.exists(config.TODAY_TODO_PATH):
        try:
            with open(config.TODAY_TODO_PATH, "r", encoding="utf-8") as file:
                content = file.read()
            for name in completed_names:
                content = re.sub(
                    rf"- \[ \] \*\*({re.escape(name)}.*?)\*\*",
                    r"- [x] **\1**",
                    content,
                )
            with open(config.TODAY_TODO_PATH, "w", encoding="utf-8") as file:
                file.write(content)
        except Exception as exc:
            print(f"同步本地计划勾选异常: {exc}")

    try:
        review_sync_service.sync_todo_completion_to_journal(completed_names)
    except Exception as exc:
        print(f"⚠️ 同步日记待办勾选异常: {exc}")

    if completed_names:
        return "✅ 已成功将飞书任务、Obsidian 待办与日记打勾完成：\n" + "\n".join(
            f"• [x] **{name}**" for name in completed_names
        )
    return None


__all__ = [
    "complete_feishu_task",
    "complete_task_by_keyword",
    "create_feishu_task",
    "delete_feishu_task",
    "list_feishu_tasks",
]
