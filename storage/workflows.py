"""Workflow metadata and safe local execution for the desktop workbench."""

from __future__ import annotations

import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.runtime.config import PROJECT_ROOT
from storage.sqlite import connect

WORKFLOWS = [
    {"key": "todo-morning", "title": "早间待办与日程", "command": "todo-morning", "schedule": "每天 06:00", "description": "整理昨天新增信息，生成今天的待办和日程建议。", "inputs": "聊天记录、知识库、已有日程", "outputs": "本地数据库、Markdown、飞书"},
    {"key": "todo-evening", "title": "晚间复盘", "command": "todo-evening", "schedule": "每天 23:00", "description": "复盘今日完成情况，归档并准备明日行动。", "inputs": "待办、日程、聊天记录", "outputs": "本地数据库、Markdown、飞书"},
    {"key": "brief", "title": "知识库简报", "command": "brief", "schedule": "每天 06:30", "description": "从本地知识库提炼当天值得关注的内容。", "inputs": "Markdown 知识库", "outputs": "简报 Markdown、飞书"},
    {"key": "news", "title": "全球新闻", "command": "news", "schedule": "每天 07:45", "description": "抓取新闻源，去重、筛选并生成结构化晨报。", "inputs": "RSS/公开新闻源", "outputs": "新闻记录、Markdown、飞书"},
    {"key": "chat", "title": "聊天复盘", "command": "chat", "schedule": "每天 07:00", "description": "分析本地聊天记录中的事项、承诺和风险。", "inputs": "本地聊天导出", "outputs": "复盘 Markdown、待办候选"},
    {"key": "fitness", "title": "饮食与运动", "command": "fitness", "schedule": "按需", "description": "处理饮食和运动记录，保留可追溯的估算与确认状态。", "inputs": "图片、文本、SQLite", "outputs": "健康记录、统计"},
    {"key": "fund", "title": "基金评估", "command": "fund", "schedule": "每天 14:00", "description": "读取持仓和市场快照，生成风险提示与观察建议。", "inputs": "基金记录、公开行情", "outputs": "评估记录、飞书"},
]


def list_workflows() -> list[dict]:
    return WORKFLOWS


def list_runs(database_path: str | Path, limit: int = 20) -> list[dict]:
    with connect(database_path) as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()]


def run_workflow(key: str, database_path: str | Path) -> dict:
    workflow = next((item for item in WORKFLOWS if item["key"] == key), None)
    if workflow is None:
        raise ValueError("workflow_not_found")
    run_id = uuid.uuid4().hex
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"workflow-{key}-{run_id[:8]}.log"
    with connect(database_path) as db:
        db.execute(
            "INSERT INTO workflow_runs(id, workflow_key, status, log_path) VALUES (?, ?, 'running', ?)",
            (run_id, key, str(log_path)),
        )
    thread = threading.Thread(
        target=_execute, args=(run_id, workflow["command"], database_path, log_path), daemon=True
    )
    thread.start()
    return {"run_id": run_id, "workflow_key": key, "status": "running"}


def _execute(run_id: str, command: str, database_path: str | Path, log_path: Path) -> None:
    started = datetime.now(timezone.utc).isoformat()
    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "main.py", command],
                cwd=PROJECT_ROOT,
                env={**__import__("os").environ, "PYTHONPATH": str(PROJECT_ROOT)},
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            code = process.wait()
        status = "success" if code == 0 else "failed"
        error = None if code == 0 else f"exit_code={code}"
    except OSError as exc:
        code, status, error = None, "failed", str(exc)
    with connect(database_path) as db:
        db.execute(
            "UPDATE workflow_runs SET status=?, finished_at=?, exit_code=?, error_message=? WHERE id=?",
            (status, datetime.now(timezone.utc).isoformat(), code, error, run_id),
        )
