from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderEvalEvidence:
    provider: str
    model: str
    task_count: int = 0
    plan_quality_pass_rate: float = 0.0
    patch_quality_pass_rate: float = 0.0
    context_precision: float = 0.0
    human_edit_distance: float | None = None
    cost_per_run: float | None = None
    latency_ms: float | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ProviderEvalEvidence":
        return cls(
            provider=str(value.get("provider") or "unknown"),
            model=str(value.get("model") or "unknown"),
            task_count=max(int(cls._number(value.get("task_count"), default=0)), 0),
            plan_quality_pass_rate=cls._rate(value.get("plan_quality_pass_rate")),
            patch_quality_pass_rate=cls._rate(value.get("patch_quality_pass_rate")),
            context_precision=cls._rate(value.get("context_precision")),
            human_edit_distance=cls._optional_rate(value.get("human_edit_distance")),
            cost_per_run=cls._optional_nonnegative(value.get("cost_per_run")),
            latency_ms=cls._optional_nonnegative(value.get("latency_ms")),
        )

    @staticmethod
    def _number(value: Any, *, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _rate(cls, value: Any) -> float:
        return min(max(cls._number(value), 0.0), 1.0)

    @classmethod
    def _optional_rate(cls, value: Any) -> float | None:
        if value is None:
            return None
        return cls._rate(value)

    @classmethod
    def _optional_nonnegative(cls, value: Any) -> float | None:
        if value is None:
            return None
        return max(cls._number(value), 0.0)


@dataclass(frozen=True)
class ProviderComparisonResult:
    provider: str
    model: str
    task_count: int
    quality_score: float
    plan_quality_pass_rate: float
    patch_quality_pass_rate: float
    context_precision: float
    human_edit_distance: float | None
    cost_per_run: float | None
    latency_ms: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "task_count": self.task_count,
            "quality_score": self.quality_score,
            "plan_quality_pass_rate": self.plan_quality_pass_rate,
            "patch_quality_pass_rate": self.patch_quality_pass_rate,
            "context_precision": self.context_precision,
            "human_edit_distance": self.human_edit_distance,
            "cost_per_run": self.cost_per_run,
            "latency_ms": self.latency_ms,
        }


class ProviderComparisonScorer:
    def score_all(self, evidence_items: list[ProviderEvalEvidence]) -> list[ProviderComparisonResult]:
        results = [self.score(evidence) for evidence in evidence_items]
        return sorted(
            results,
            key=lambda result: (
                -result.quality_score,
                result.cost_per_run if result.cost_per_run is not None else float("inf"),
                result.latency_ms if result.latency_ms is not None else float("inf"),
                result.provider,
                result.model,
            ),
        )

    def score(self, evidence: ProviderEvalEvidence) -> ProviderComparisonResult:
        edit_quality = 1.0 - evidence.human_edit_distance if evidence.human_edit_distance is not None else 0.0
        quality_score = round(
            (0.35 * evidence.patch_quality_pass_rate)
            + (0.25 * evidence.plan_quality_pass_rate)
            + (0.25 * evidence.context_precision)
            + (0.15 * edit_quality),
            4,
        )
        return ProviderComparisonResult(
            provider=evidence.provider,
            model=evidence.model,
            task_count=evidence.task_count,
            quality_score=quality_score,
            plan_quality_pass_rate=evidence.plan_quality_pass_rate,
            patch_quality_pass_rate=evidence.patch_quality_pass_rate,
            context_precision=evidence.context_precision,
            human_edit_distance=evidence.human_edit_distance,
            cost_per_run=evidence.cost_per_run,
            latency_ms=evidence.latency_ms,
        )
