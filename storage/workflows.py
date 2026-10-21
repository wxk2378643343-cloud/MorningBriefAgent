"""Workflow metadata, scheduling integration, and safe local execution for the desktop workbench."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.runtime.config import PROJECT_ROOT
from storage.sqlite import connect

DEFAULT_WORKFLOWS = [
    {
        "key": "todo-morning",
        "title": "早间待办与日程",
        "command": "todo-morning",
        "default_time": "06:00",
        "schedule_type": "daily",
        "enabled": True,
        "description": "整理昨天新增信息，智能生成今日行动清单与飞书日程建议。",
        "inputs": "聊天记录、知识库、已有日程",
        "outputs": "本地数据库、Markdown、飞书卡片",
        "task_name": "DailyTodoMorningPush",
        "category": "planning"
    },
    {
        "key": "brief",
        "title": "知识库简报智能体",
        "command": "brief",
        "default_time": "06:30",
        "schedule_type": "manual",
        "enabled": False,
        "description": "从本地 Markdown 知识库深度提炼今日核心关注点与行动清单。",
        "inputs": "Markdown 知识库",
        "outputs": "简报 Markdown、飞书推送",
        "task_name": "",
        "category": "knowledge"
    },
    {
        "key": "chat",
        "title": "聊天复盘智能体",
        "command": "chat",
        "default_time": "07:00",
        "schedule_type": "manual",
        "enabled": False,
        "description": "多维分析本地聊天记录中的承诺、待办候选与关键风险点。",
        "inputs": "本地聊天导出文件",
        "outputs": "复盘 Markdown、待办候选",
        "task_name": "",
        "category": "communication"
    },
    {
        "key": "news",
        "title": "全球热点晨报",
        "command": "news",
        "default_time": "07:45",
        "schedule_type": "manual",
        "enabled": False,
        "description": "聚合新闻源，去重筛选并智能生成早间结构化全球快讯。",
        "inputs": "RSS / 公开新闻源",
        "outputs": "新闻数据库、Markdown、飞书",
        "task_name": "",
        "category": "information"
    },
    {
        "key": "fund",
        "title": "基金量化投顾",
        "command": "fund",
        "default_time": "14:00",
        "schedule_type": "manual",
        "enabled": False,
        "description": "读取持仓与全球实时行情快照，智能评估春节盈利目标与调仓提示。",
        "inputs": "持仓记录、新浪全球实时行情",
        "outputs": "评估报告、飞书富文本卡片",
        "task_name": "",
        "category": "finance"
    },
    {
        "key": "todo-evening",
        "title": "晚间复盘总结",
        "command": "todo-evening",
        "default_time": "23:00",
        "schedule_type": "daily",
        "enabled": True,
        "description": "全面复盘今日完成情况，级联同步 Markdown 日/周/月周期复盘。",
        "inputs": "待办清单、飞书日程、聊天流",
        "outputs": "本地数据库、Markdown 周期复盘、飞书",
        "task_name": "DailyTodoEveningReview",
        "category": "planning"
    },
    {
        "key": "fitness",
        "title": "饮食与运动健康",
        "command": "fitness",
        "default_time": "21:30",
        "schedule_type": "manual",
        "enabled": False,
        "description": "处理饮食热量与运动记录，保留可追溯的估算与确认状态。",
        "inputs": "饮食图片、文本描述、SQLite",
        "outputs": "健康统计数据库、多模态卡片",
        "task_name": "",
        "category": "lifestyle"
    },
]


def _calculate_next_run(schedule_time: str, enabled: bool) -> str:
    """Calculate human-readable next trigger time."""
    if not enabled or not schedule_time or ":" not in schedule_time:
        return "未启用定时"
    try:
        now = datetime.now()
        target_hour, target_min = map(int, schedule_time.split(":")[:2])
        target_today = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
        if target_today > now:
            diff = target_today - now
            hours, remainder = divmod(int(diff.total_seconds()), 3600)
            mins = remainder // 60
            if hours > 0:
                return f"今日 {schedule_time} (约 {hours}小时{mins}分后)"
            return f"今日 {schedule_time} (约 {mins}分钟后)"
        else:
            diff = (target_today + timedelta(days=1)) - now
            hours, remainder = divmod(int(diff.total_seconds()), 3600)
            mins = remainder // 60
            return f"明日 {schedule_time} (约 {hours}小时{mins}分后)"
    except Exception:
        return f"每天 {schedule_time}"


def _ensure_tables(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS local_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            is_secret INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            workflow_key TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            exit_code INTEGER,
            log_path TEXT,
            error_message TEXT
        )
        """
    )


def list_workflows(database_path: str | Path | None = None) -> list[dict]:
    """Return all workflows with runtime overrides, latest run status, and schedule details."""
    overrides: dict[str, dict] = {}
    latest_runs: dict[str, dict] = {}

    if database_path:
        try:
            with connect(database_path) as db:
                _ensure_tables(db)
                rows = db.execute(
                    "SELECT key, value FROM local_settings WHERE key LIKE 'workflow_schedule:%'"
                ).fetchall()
                for row in rows:
                    w_key = row["key"].replace("workflow_schedule:", "")
                    try:
                        overrides[w_key] = json.loads(row["value"])
                    except Exception:
                        pass

                # Fetch the latest run for each workflow_key
                run_rows = db.execute(
                    """
                    SELECT r1.* FROM workflow_runs r1
                    INNER JOIN (
                        SELECT workflow_key, MAX(started_at) as max_started
                        FROM workflow_runs GROUP BY workflow_key
                    ) r2 ON r1.workflow_key = r2.workflow_key AND r1.started_at = r2.max_started
                    """
                ).fetchall()
                for r in run_rows:
                    latest_runs[r["workflow_key"]] = dict(r)
        except Exception:
            pass

    results = []
    for item in DEFAULT_WORKFLOWS:
        key = item["key"]
        custom = overrides.get(key, {})
        time_val = custom.get("time", item["default_time"])
        enabled_val = custom.get("enabled", item["enabled"])
        schedule_display = f"每天 {time_val}" if enabled_val else "按需 (已暂停)"

        last_run_item = latest_runs.get(key)
        duration_sec = None
        if last_run_item and last_run_item.get("started_at") and last_run_item.get("finished_at"):
            try:
                s = datetime.fromisoformat(last_run_item["started_at"])
                f = datetime.fromisoformat(last_run_item["finished_at"])
                duration_sec = round((f - s).total_seconds(), 1)
            except Exception:
                pass

        merged = {
            **item,
            "schedule": schedule_display,
            "schedule_time": time_val,
            "enabled": enabled_val,
            "next_run_hint": _calculate_next_run(time_val, enabled_val),
            "last_run": {
                "id": last_run_item["id"] if last_run_item else None,
                "status": last_run_item["status"] if last_run_item else None,
                "started_at": last_run_item["started_at"] if last_run_item else None,
                "finished_at": last_run_item["finished_at"] if last_run_item else None,
                "duration_seconds": duration_sec,
                "error_message": last_run_item["error_message"] if last_run_item else None,
            } if last_run_item else None
        }
        results.append(merged)

    return results


def update_workflow_schedule(
    key: str,
    schedule_time: str | None,
    enabled: bool | None,
    database_path: str | Path,
) -> dict:
    """Update and persist schedule time or toggle state for a workflow agent."""
    workflow = next((item for item in DEFAULT_WORKFLOWS if item["key"] == key), None)
    if workflow is None:
        raise ValueError("workflow_not_found")

    with connect(database_path) as db:
        _ensure_tables(db)
        # Load current stored settings
        row = db.execute(
            "SELECT value FROM local_settings WHERE key = ?", (f"workflow_schedule:{key}",)
        ).fetchone()
        current = json.loads(row["value"]) if row else {}

        new_time = schedule_time if schedule_time is not None else current.get("time", workflow["default_time"])
        new_enabled = enabled if enabled is not None else current.get("enabled", workflow["enabled"])

        new_val = json.dumps({"time": new_time, "enabled": new_enabled})
        db.execute(
            """
            INSERT INTO local_settings(key, value, is_secret, updated_at)
            VALUES (?, ?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
            """,
            (f"workflow_schedule:{key}", new_val),
        )

    # Optional: trigger background Windows task sync if available
    return {
        "key": key,
        "schedule_time": new_time,
        "enabled": new_enabled,
        "schedule": f"每天 {new_time}" if new_enabled else "按需 (已暂停)",
        "next_run_hint": _calculate_next_run(new_time, new_enabled),
    }


def list_runs(database_path: str | Path, limit: int = 30) -> list[dict]:
    with connect(database_path) as db:
        rows = db.execute(
            "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        runs = []
        for r in rows:
            d = dict(r)
            if d.get("started_at") and d.get("finished_at"):
                try:
                    s = datetime.fromisoformat(d["started_at"])
                    f = datetime.fromisoformat(d["finished_at"])
                    d["duration_seconds"] = round((f - s).total_seconds(), 1)
                except Exception:
                    d["duration_seconds"] = None
            else:
                d["duration_seconds"] = None
            runs.append(d)
        return runs


def get_workflow_log(run_id: str, database_path: str | Path) -> dict:
    """Read log content for a specific run."""
    with connect(database_path) as db:
        row = db.execute(
            "SELECT id, workflow_key, status, log_path, started_at, finished_at, error_message FROM workflow_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if not row:
            return {"error": "run_not_found", "run_id": run_id, "content": "未找到对应的执行记录"}

        info = dict(row)
        log_path_str = info.get("log_path")
        if not log_path_str:
            return {"run_id": run_id, "info": info, "content": "此运行未记录日志路径"}

        log_path = Path(log_path_str)
        if not log_path.exists():
            return {
                "run_id": run_id,
                "info": info,
                "content": f"日志文件尚未生成或已被清理：\n{log_path_str}",
            }

        try:
            # Read tail of log up to 100KB
            size = log_path.stat().st_size
            max_bytes = 102400
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                if size > max_bytes:
                    f.seek(size - max_bytes)
                    content = "…… [前面日志已折叠截断] ……\n" + f.read()
                else:
                    content = f.read()
            return {"run_id": run_id, "info": info, "content": content or "日志为空（进程无标准输出）"}
        except Exception as exc:
            return {"run_id": run_id, "info": info, "content": f"读取日志出错：{exc}"}


def run_workflow(key: str, database_path: str | Path) -> dict:
    workflow = next((item for item in DEFAULT_WORKFLOWS if item["key"] == key), None)
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
    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "main.py", command],
                cwd=PROJECT_ROOT,
                env={
                    **__import__("os").environ,
                    "PYTHONPATH": str(PROJECT_ROOT),
                    "MORNINGBRIEF_METADATA_DATABASE_PATH": str(Path(database_path).resolve()),
                },
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


def sync_windows_tasks(database_path: str | Path) -> dict:
    """Run windows task registration script to apply active schedules."""
    ps1 = PROJECT_ROOT / "scripts" / "register_windows_tasks.ps1"
    if not ps1.exists():
        return {"ok": False, "message": "未找到 register_windows_tasks.ps1 脚本"}

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return {
            "ok": res.returncode == 0,
            "message": "Windows 计划任务已成功同步与重载" if res.returncode == 0 else f"同步失败：{res.stderr.strip()}",
            "output": res.stdout,
        }
    except Exception as exc:
        return {"ok": False, "message": f"同步触发异常：{exc}"}
