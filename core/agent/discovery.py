"""Safe provider and channel discovery for the local onboarding flow."""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from core.runtime import config


@dataclass(frozen=True)
class CapabilityStatus:
    name: str
    kind: str
    available: bool
    configured: bool
    detail: str


def discover_providers() -> list[CapabilityStatus]:
    """Return availability without exposing credentials or starting processes."""
    return [
        CapabilityStatus(
            name="deepseek",
            kind="api",
            available=bool(config.DEEPSEEK_API_KEY),
            configured=bool(config.DEEPSEEK_API_KEY),
            detail=(
                f"model={config.DEEPSEEK_MODEL}"
                if config.DEEPSEEK_API_KEY else "API key not configured"
            ),
        ),
        CapabilityStatus(
            name="agy",
            kind="local_process",
            available=_local_agent_available(),
            configured=bool(config.AGY_BRAIN_DIR or config.AGENTAPI_EXE),
            detail=_agy_detail(),
        ),
        CapabilityStatus(
            name="claude",
            kind="api",
            available=bool(os.getenv("ANTHROPIC_API_KEY")),
            configured=bool(os.getenv("ANTHROPIC_API_KEY")),
            detail="configured via environment" if os.getenv("ANTHROPIC_API_KEY")
            else "API key not configured",
        ),
        CapabilityStatus(
            name="codex",
            kind="local_or_api",
            available=bool(os.getenv("CODEX_HOME") or shutil.which("codex")),
            configured=bool(os.getenv("CODEX_HOME") or shutil.which("codex")),
            detail="local command or runtime detected"
            if (os.getenv("CODEX_HOME") or shutil.which("codex"))
            else "runtime not detected",
        ),
    ]


def discover_channels() -> list[CapabilityStatus]:
    return [
        CapabilityStatus(
            name="feishu",
            kind="channel",
            available=bool(config.FEISHU_APP_ID and config.FEISHU_APP_SECRET),
            configured=bool(config.FEISHU_APP_ID and config.FEISHU_APP_SECRET),
            detail="app credentials configured"
            if (config.FEISHU_APP_ID and config.FEISHU_APP_SECRET)
            else "app credentials not configured",
        )
    ]


def discovery_snapshot() -> dict[str, list[dict[str, object]]]:
    return {
        "providers": [asdict(item) for item in discover_providers()],
        "channels": [asdict(item) for item in discover_channels()],
    }


def _local_agent_available() -> bool:
    if config.AGENTAPI_EXE and Path(config.AGENTAPI_EXE).exists():
        return True
    return bool(os.getenv("AGY_PROCESS_RUNNING") == "1")


def _agy_detail() -> str:
    if _local_agent_available():
        return "local Agent executable or process detected"
    if config.AGY_BRAIN_DIR:
        return "local Agent directory configured; process not confirmed"
    return "local Agent not detected"
