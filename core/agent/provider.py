"""Unified Agent port for non-conversational tasks.

The interactive Feishu conversation intentionally remains on the existing
single AGY conversation. Batch tasks use this adapter so prompt construction,
error handling and structured-output parsing are consistent.
"""
from __future__ import annotations

import json
import re
from storage.usage import UsageTimer, estimate_tokens, record_usage
from typing import Any, Optional

try:
    from . import agy_bridge
except ImportError:
    from core.agent import agy_bridge


def ask_text(task: str, prompt: str, context: str = "") -> str:
    """Run a task through the existing AGY bridge and return text."""
    timer = UsageTimer()
    result = agy_bridge.ask_native_agy(task, prompt, context)
    record_usage(
        task=task,
        provider="agy",
        input_tokens=estimate_tokens(prompt + context),
        output_tokens=estimate_tokens(result),
        duration_ms=timer.elapsed_ms(),
        status="error" if result.startswith("❌") else "success",
    )
    return result


def ask_json(
    task: str,
    prompt: str,
    context: str = "",
) -> Optional[dict[str, Any]]:
    """Run a task and parse one JSON object from the Agent response.

    The bridge still uses the user's single conversation by design. This
    function only standardizes structured output for batch workflows.
    """
    result = ask_text(task, prompt, context)
    if not result or result.startswith("❌"):
        return None
    fenced = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        result,
        re.DOTALL | re.IGNORECASE,
    )
    raw = fenced.group(1) if fenced else result.strip()
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
