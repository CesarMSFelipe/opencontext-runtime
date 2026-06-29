"""Runtime Optimizer (PR-000.3) — recommend-only cache/context/profile advice.

Reads aggregate cache hit/miss telemetry (``CacheStats``) plus optional token
telemetry (``learning/token_optimizer.TokenOptimizer``) and returns
``RuntimeOptimizationRecommendation``s. It is structurally recommend-only: it is
constructed with **no** config/mutation port, so it cannot apply anything — it
only emits advice for a downstream consumer (PR-011 Runtime Intelligence) to read
through a port, never imported directly here.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.cache.base import CacheStats
from opencontext_core.optimization.recommendations import (
    RecommendationTarget,
    RuntimeOptimizationRecommendation,
)


class RuntimeOptimizer:
    """Turns observed telemetry into recommendations. Never applies them."""

    def __init__(
        self,
        *,
        cache_stats: CacheStats | None = None,
        token_optimizer: Any | None = None,
        enabled: bool = False,
        low_hit_rate_threshold: float = 0.3,
        min_samples: int = 5,
    ) -> None:
        self._cache_stats = cache_stats
        self._token_optimizer = token_optimizer
        self.enabled = enabled
        self._low_hit_rate_threshold = low_hit_rate_threshold
        self._min_samples = min_samples

    def recommend(self) -> list[RuntimeOptimizationRecommendation]:
        """Return recommendations from telemetry; empty when disabled.

        Recommend-only: this method reads telemetry and returns advice. It does
        not (and cannot) mutate any cache/context/profile configuration.
        """

        if not self.enabled:
            return []
        recs: list[RuntimeOptimizationRecommendation] = []
        recs.extend(self._cache_recommendations())
        recs.extend(self._token_recommendations())
        return recs

    def _cache_recommendations(self) -> list[RuntimeOptimizationRecommendation]:
        if self._cache_stats is None:
            return []
        recs: list[RuntimeOptimizationRecommendation] = []
        for cache_type, counts in sorted(self._cache_stats.by_type.items()):
            hits = counts.get("hits", 0)
            misses = counts.get("misses", 0)
            total = hits + misses
            if total < self._min_samples:
                continue
            hit_rate = hits / total
            if hit_rate < self._low_hit_rate_threshold:
                recs.append(
                    RuntimeOptimizationRecommendation(
                        target=RecommendationTarget.cache,
                        title=f"Low hit rate for {cache_type} cache",
                        rationale=(
                            f"{cache_type} cache hit rate is {hit_rate:.0%} over {total} "
                            f"lookups ({misses} recomputes); raising TTL or widening "
                            f"eligibility would cut recompute cost."
                        ),
                        evidence_ref=f"cache_stats.by_type.{cache_type}",
                        expected_effect=f"reduce {cache_type} recomputes",
                        confidence=min(1.0, total / 50),
                    )
                )
        return recs

    def _token_recommendations(self) -> list[RuntimeOptimizationRecommendation]:
        if self._token_optimizer is None:
            return []
        try:
            report = self._token_optimizer.report_savings()
        except Exception:
            return []
        recs: list[RuntimeOptimizationRecommendation] = []
        by_op = report.get("by_operation_type", {}) if isinstance(report, dict) else {}
        for op_type, detail in sorted(by_op.items()):
            projected = detail.get("projected_savings", 0)
            if projected <= 0:
                continue
            target = (
                RecommendationTarget.profile
                if detail.get("efficiency", 1.0) < 0.5
                else RecommendationTarget.context
            )
            recs.append(
                RuntimeOptimizationRecommendation(
                    target=target,
                    title=f"Token budget over-provisioned for {op_type}",
                    rationale=(
                        f"{op_type} shows efficiency {detail.get('efficiency', 0)} with "
                        f"~{projected} projected wasted tokens; tightening the "
                        f"{target.value} budget would recover them."
                    ),
                    evidence_ref=f"token_optimizer.report_savings.by_operation_type.{op_type}",
                    expected_effect=f"reduce ~{projected} tokens",
                    confidence=0.5,
                )
            )
        return recs
