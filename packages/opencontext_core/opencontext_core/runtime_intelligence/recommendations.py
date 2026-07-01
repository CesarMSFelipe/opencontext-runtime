"""Runtime Intelligence — recommendation consumer surface (PR-000.3 / PR-011).

This module re-exports the PR-000.3 cache-flavoured recommendation
surface and adds a thin ``cache_low_hit_rate_recommendation`` factory so
Runtime Intelligence (PR-011) can build advice from cache telemetry
without importing the cache leaf directly. The PR-011 optimizer will
merge this consumer into its own surface; PR-000.3 keeps it as a small
adapter so the leaf + the recommendation shape stay decoupled.
"""

from __future__ import annotations

from opencontext_core.optimization.recommendations import (
    RecommendationTarget,
    RuntimeOptimizationRecommendation,
)


def cache_low_hit_rate_recommendation(
    *,
    cache_type: str,
    hit_rate: float,
    total_lookups: int,
) -> RuntimeOptimizationRecommendation:
    """Build a `cache.too_low_hit_rate` recommendation backed by hit-rate telemetry."""
    return RuntimeOptimizationRecommendation(
        target=RecommendationTarget.cache,
        title=f"Low hit rate for {cache_type} cache",
        rationale=(
            f"{cache_type} cache hit rate is {hit_rate:.0%} over {total_lookups} "
            f"lookups; raising TTL or widening eligibility would cut recompute cost."
        ),
        evidence_ref=f"cache_stats.by_type.{cache_type}",
        expected_effect=f"reduce {cache_type} recomputes",
        confidence=min(1.0, total_lookups / 50),
    )


__all__ = [
    "RecommendationTarget",
    "RuntimeOptimizationRecommendation",
    "cache_low_hit_rate_recommendation",
]