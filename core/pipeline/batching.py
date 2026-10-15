"""Size-aware batching for Agent inputs without slicing serialized JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Generic, Iterable, TypeVar


T = TypeVar("T")


class OversizedBatchItem(ValueError):
    """Raised when one item cannot fit into an otherwise empty batch."""


@dataclass(frozen=True)
class AgentBatcher(Generic[T]):
    """Partition values by the size of their complete serialized envelope."""

    max_chars: int = 18000

    @staticmethod
    def serialize(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    def partition(
        self,
        items: Iterable[T],
        *,
        envelope: Callable[[list[T]], Any] | None = None,
    ) -> list[list[T]]:
        wrap = envelope or (lambda values: values)
        batches: list[list[T]] = []
        current: list[T] = []
        for item in items:
            candidate = [*current, item]
            if len(self.serialize(wrap(candidate))) <= self.max_chars:
                current = candidate
                continue
            if current:
                batches.append(current)
                current = []
            if len(self.serialize(wrap([item]))) > self.max_chars:
                raise OversizedBatchItem(
                    "A single Agent input item exceeds the configured batch limit"
                )
            current = [item]
        if current:
            batches.append(current)
        return batches
