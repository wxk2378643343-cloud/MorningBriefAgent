"""Configuration and dependency diagnostics for MorningBriefAgent."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

try:
    from . import config
    from ..integrations.sync_outbox import sync_outbox
except ImportError:
    from core.runtime import config
    from core.integrations.sync_outbox import sync_outbox


def _check_path(label: str, value: str, must_exist: bool = False) -> str:
    if not value:
        return f"[SKIP] {label}: 未配置"
    path = Path(value)
    if must_exist and not path.exists():
        return f"[WARN] {label}: 路径不存在 ({path})"
    return f"[OK] {label}: {path}"


def run_checks() -> list[str]:
    """Return human-readable checks without contacting external services."""
    checks = [
        _check_path("Agent executable", config.AGENTAPI_EXE),
        _check_path("Agent brain directory", config.AGY_BRAIN_DIR),
        _check_path("Configured email directories", ";".join(config.EMAIL_INBOX_DIRS)),
        _check_path("Todo output", config.TODAY_TODO_PATH),
        _check_path("Review daily output", config.REVIEW_DAILY_DIR),
        _check_path("News world sources", ";".join(config.NEWS_WORLD_URLS)),
    ]
    if config.FEISHU_APP_ID and config.FEISHU_APP_SECRET:
        checks.append("[OK] Feishu credentials: 已配置（值不显示）")
    else:
        checks.append("[WARN] Feishu credentials: 未完整配置")
    if config.FEISHU_ALLOWED_OPEN_IDS:
        checks.append("[OK] Feishu sender allowlist: 已配置")
    else:
        checks.append("[WARN] Feishu sender allowlist: 为空")
    pending = len(sync_outbox.pending())
    checks.append(
        f"[WARN] Sync outbox: {pending} 项待重试/待对账"
        if pending else "[OK] Sync outbox: 无待处理记录"
    )
    return checks


def main() -> int:
    for line in run_checks():
        print(line)
    return 0
