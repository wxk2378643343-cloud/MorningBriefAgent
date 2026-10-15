"""Small, domain-neutral quality contracts shared by scheduled workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class SourceStatus:
    name: str
    item_count: int
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualityReport:
    ready: bool
    sources: tuple[SourceStatus, ...] = field(default_factory=tuple)
    issues: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def evaluate(
        cls,
        sources: Iterable[SourceStatus],
        *,
        minimum_total: int = 1,
        minimum_healthy_sources: int = 1,
    ) -> "QualityReport":
        values = tuple(sources)
        total = sum(max(0, source.item_count) for source in values)
        healthy = sum(1 for source in values if source.ok and source.item_count > 0)
        issues = tuple(
            source.detail or f"{source.name} 暂无有效数据"
            for source in values
            if not source.ok or source.item_count <= 0
        )
        return cls(
            ready=total >= minimum_total and healthy >= minimum_healthy_sources,
            sources=values,
            issues=issues,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "sources": [source.to_dict() for source in self.sources],
            "issues": list(self.issues),
        }

    def status_text(self) -> str:
        return " · ".join(
            f"{'✅' if source.ok and source.item_count else '⚠️'} "
            f"{source.name} {source.item_count}条"
            for source in self.sources
        )
