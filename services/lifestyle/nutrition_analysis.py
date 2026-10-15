"""Source-grounded nutrition estimation; estimates never become confirmed facts."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from core.agent import context as agent_context
from core.agent import provider as agent_provider
from storage.lifestyle import (
    confirm_meal,
    get_latest_pending_meal,
    save_meal_estimate,
)


MEAL_CATEGORIES = frozenset({"早餐", "午餐", "晚餐", "加餐"})


def estimate_meal(
    *,
    fact_id: str,
    category: str,
    text: str,
    image_paths: list[str] | tuple[str, ...] = (),
    ask_json: Callable[..., Any] | None = None,
    database_path: str | None = None,
) -> dict[str, Any]:
    """Ask the Agent for a bounded estimate and persist only pending values."""
    if category not in MEAL_CATEGORIES:
        return {"fact_id": fact_id, "status": "not_meal"}
    ask_json = ask_json or agent_provider.ask_json
    prompt = agent_context.build_prompt(
        task=(
            "你是营养记录解析器。只根据用户文字和明确可见的输入估算这顿餐食，"
            "不要把不确定内容当成事实。严格输出 JSON："
            "{\"calories_estimated\": number|null,\"protein_estimated\": number|null,"
            "\"confidence\": number,\"basis\":\"依据\",\"missing\":[]}。"
            "无法可靠估算时返回 null；不要编造食物、重量或营养目标。"
        ),
        query=f"解析{category}，仅生成待确认估算。",
        context=json.dumps({
            "fact_id": fact_id,
            "category": category,
            "text": text,
            "image_paths": list(image_paths),
        }, ensure_ascii=False),
    )
    try:
        result = ask_json("meal-nutrition-estimate", prompt)
    except Exception as exc:
        print(f"⚠️ 餐食热量估算暂不可用: {exc}")
        return {"fact_id": fact_id, "status": "unavailable"}
    if not isinstance(result, dict):
        return {"fact_id": fact_id, "status": "invalid"}

    def bounded_number(key: str) -> float | None:
        value = result.get(key)
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if 0 <= number <= 10000 else None

    calories = bounded_number("calories_estimated")
    protein = bounded_number("protein_estimated")
    confidence = bounded_number("confidence")
    if calories is None and protein is None:
        return {
            "fact_id": fact_id,
            "status": "insufficient_data",
            "basis": str(result.get("basis", "")).strip(),
        }
    save_meal_estimate(
        fact_id,
        calories=calories,
        protein=protein,
        database_path=database_path,
    )
    return {
        "fact_id": fact_id,
        "status": "pending",
        "calories_estimated": calories,
        "protein_estimated": protein,
        "confidence": confidence,
        "basis": str(result.get("basis", "")).strip(),
    }


def handle_confirmation(
    text: str,
    *,
    actor: str,
    database_path: str | None = None,
) -> str | None:
    """Handle an explicit user confirmation for the latest pending meal."""
    match = re.search(
        r"确认(?:热量|卡路里)\s*[:：]?\s*(\d+(?:\.\d+)?)",
        text or "",
    )
    if not match:
        return None
    calories = float(match.group(1))
    pending = get_latest_pending_meal(database_path=database_path)
    if not pending:
        return "目前没有待确认的餐食热量记录。"
    if not confirm_meal(
        pending["fact_id"],
        calories=calories,
        actor=actor,
        database_path=database_path,
    ):
        return "热量确认失败，请稍后重试。"
    return (
        f"✅ 已确认本次餐食热量：{calories:g} kcal。\n"
        "该数值已进入正式统计。"
    )
