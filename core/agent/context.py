"""Generic local-context discovery for agent-first workflows.

Personal goals, schedules and preferences belong in the user's local knowledge
base, never in application source code. This module only discovers configured
Markdown context and prepares it for the local agent.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "").replace(";", ",")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _candidate_files() -> Iterable[Path]:
    configured_files = _csv_env("AGENT_CONTEXT_FILES")
    if configured_files:
        yield from (Path(item) for item in configured_files)
        return
    for directory_name in _csv_env("AGENT_CONTEXT_DIRS"):
        directory = Path(directory_name)
        if directory.is_dir():
            yield from directory.rglob("*.md")


def collect_context(query: str = "", max_files: int = 8, max_chars: int = 12000) -> str:
    """Collect a bounded, query-relevant snapshot from local Markdown files."""
    query_terms = {
        term.lower()
        for term in query.replace("/", " ").replace("\\", " ").split()
        if len(term) >= 2
    }
    ranked: list[tuple[int, float, Path]] = []
    for path in _candidate_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            score = sum(text.lower().count(term) for term in query_terms)
            ranked.append((score, path.stat().st_mtime, path))
        except OSError:
            continue
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)

    chunks: list[str] = []
    used = 0
    for _, _, path in ranked[:max_files]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            continue
        if not text:
            continue
        remaining = max_chars - used
        if remaining <= 0:
            break
        excerpt = text[:remaining]
        chunks.append(f"【来源：{path}】\n{excerpt}")
        used += len(excerpt)
    return "\n\n".join(chunks)


def build_prompt(task: str, query: str = "", context: str = "") -> str:
    """Build a neutral prompt that asks the local agent to infer, not assume."""
    context = context or collect_context(query)
    return (
        "你是一个本地个人知识库分析助手。\n"
        "只根据用户问题和提供的本地资料进行判断，不要猜测用户的目标、作息、职业、"
        "学校、身体状况、投资偏好或人际关系。\n"
        "如果资料不足，请明确说明缺口，并给出需要用户补充的最小信息。\n\n"
        f"【任务】\n{task}\n\n"
        f"【用户问题】\n{query or '请分析当前资料并提出下一步建议。'}\n\n"
        f"【本地资料】\n{context or '暂无可用本地资料。'}"
    )
