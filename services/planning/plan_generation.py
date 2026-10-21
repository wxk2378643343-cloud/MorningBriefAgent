"""Agent-backed plan generation and staged-plan persistence."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from core.agent import context as agent_context
from core.agent import provider as agent_provider
from core.agent.contracts import AgentPlan
from core.runtime import config
from storage.planning import persist_plan
from storage.workspace import active_database_path
from services.knowledge import project_plan


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STAGED_PLAN_FILE = Path(config.STAGED_PLAN_PATH)


def get_default_baseline_todos() -> List[str]:
    """Return no personal defaults; the local agent supplies the plan."""
    return []


def get_default_schedule_slots(target_date: date) -> List[Dict[str, str]]:
    """Return no hard-coded personal schedule."""
    return []


def generate_agent_plan(
    target_date: str,
    analysis: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Ask the local agent for a validated plan based on configured context."""
    analysis_context = json.dumps(analysis or {}, ensure_ascii=False, indent=2)
    prompt = agent_context.build_prompt(
        task=(
            "你是计划编排器。为指定日期生成一个可执行计划，只能使用上一步事实分析"
            "中 valid_items 和 constraints 明确存在的目标与约束。"
            "输出严格 JSON：{\"todos\": [\"...\"], \"schedule_slots\": "
            "[{\"name\":\"...\",\"start\":\"HH:MM\",\"end\":\"HH:MM\","
            "\"summary\":\"...\",\"desc\":\"...\"}]}。资料不足时返回空数组，"
            "不要自行发明学习、运动、工作、生活目标或时间。没有明确时间约束的事项"
            "可以进入 todos，但不得强行生成 schedule_slots。"
        ),
        query=f"请为 {target_date} 生成计划。",
        context=f"【上一步事实分析】\n{analysis_context}",
    )
    try:
        data = agent_provider.ask_json("daily-plan", prompt)
        if isinstance(data, dict):
            data.setdefault("todos", [])
            data.setdefault("schedule_slots", [])
            data["date"] = target_date
            try:
                return AgentPlan.from_dict(data, target_date).to_dict()
            except ValueError as exc:
                print(f"⚠️ Agent 计划契约校验失败: {exc}")
    except Exception as exc:
        print(f"Agent plan unavailable: {exc}")
    return {"date": target_date, "todos": [], "schedule_slots": []}


def load_staged_plan(path: os.PathLike[str] | str | None = None) -> Dict[str, Any]:
    target = Path(path or config.STAGED_PLAN_PATH or DEFAULT_STAGED_PLAN_FILE)
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_staged_plan(
    data: Dict[str, Any],
    path: os.PathLike[str] | str | None = None,
    *,
    metadata_database_path: os.PathLike[str] | str | None = None,
    database_path: os.PathLike[str] | str | None = None,
) -> None:
    target = Path(path or config.STAGED_PLAN_PATH or DEFAULT_STAGED_PLAN_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # 1. Resolve active database and persist facts.
    # Must NOT swallow WorkspaceDatabaseUnavailableError or persistence failures!
    target_db = (
        Path(database_path).resolve()
        if database_path
        else active_database_path(metadata_database_path)
    )
    persist_plan(data, database_path=target_db)

    # 2. Markdown projection is non-blocking and isolated
    if path is None:
        try:
            project_plan(data)
        except Exception as exc:
            print(f"⚠️ Markdown 计划投影异常 (允许降级): {exc}")


__all__ = [
    "generate_agent_plan",
    "get_default_baseline_todos",
    "get_default_schedule_slots",
    "load_staged_plan",
    "save_staged_plan",
]
