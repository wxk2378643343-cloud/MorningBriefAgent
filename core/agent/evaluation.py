"""Offline, provider-neutral evaluation helpers.

The evaluator deliberately knows nothing about AGY or a remote API. Both
providers receive the same case and return the same structured contract.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    task: str
    prompt: str
    expected_keys: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationResult:
    provider: str
    case_id: str
    success: bool
    schema_valid: bool
    duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str = ""


def evaluate_provider(
    provider: str,
    cases: list[EvaluationCase],
    ask: Callable[[EvaluationCase], dict[str, Any] | None],
    *,
    estimate_tokens: Callable[[str], int] | None = None,
) -> list[EvaluationResult]:
    """Run identical cases through one provider without external side effects."""
    results: list[EvaluationResult] = []
    for case in cases:
        started = time.perf_counter()
        try:
            value = ask(case)
            valid = isinstance(value, dict) and all(
                key in value for key in case.expected_keys
            )
            results.append(EvaluationResult(
                provider=provider,
                case_id=case.case_id,
                success=valid,
                schema_valid=valid,
                duration_ms=int((time.perf_counter() - started) * 1000),
                input_tokens=estimate_tokens(case.prompt) if estimate_tokens else None,
                output_tokens=estimate_tokens(str(value)) if estimate_tokens and value else None,
                error="" if valid else "invalid structured response",
            ))
        except Exception as exc:  # one bad case must not hide provider results
            results.append(EvaluationResult(
                provider=provider,
                case_id=case.case_id,
                success=False,
                schema_valid=False,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
            ))
    return results


def compare_results(*provider_results: list[EvaluationResult]) -> dict[str, dict[str, float]]:
    """Return comparable aggregate metrics for each provider."""
    summary: dict[str, dict[str, float]] = {}
    for results in provider_results:
        if not results:
            continue
        provider = results[0].provider
        summary[provider] = {
            "cases": float(len(results)),
            "success_rate": sum(item.success for item in results) / len(results),
            "schema_valid_rate": sum(item.schema_valid for item in results) / len(results),
            "avg_duration_ms": sum(item.duration_ms for item in results) / len(results),
        }
    return summary
