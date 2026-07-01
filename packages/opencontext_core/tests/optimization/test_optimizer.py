"""REQ-cache-v2-005 — RuntimeOptimizer recommendations (evidence-backed)."""

from __future__ import annotations


class TestRuntimeOptimizer:
    def test_disabled_returns_empty(self) -> None:
        from opencontext_core.optimization import RuntimeOptimizer

        opt = RuntimeOptimizer(enabled=False)
        assert opt.recommend() == []

    def test_cache_low_hit_rate_emits_recommendation(self) -> None:
        """REQ-cache-v2-005 — 70% miss on tool_output -> `cache.too_low_hit_rate` rec."""
        from opencontext_core.cache.base import CacheStats
        from opencontext_core.optimization import RuntimeOptimizer

        stats = CacheStats(
            entries=10,
            hits=3,
            misses=7,
            by_type={"tool_output": {"hits": 3, "misses": 7}},
        )
        opt = RuntimeOptimizer(cache_stats=stats, enabled=True, low_hit_rate_threshold=0.5)
        recs = opt.recommend()
        assert len(recs) >= 1
        tool_rec = next(r for r in recs if "tool_output" in r.title)
        assert tool_rec.evidence_ref != ""
        assert "tool_output" in tool_rec.evidence_ref

    def test_recommendation_evidence_not_empty(self) -> None:
        """REQ-cache-v2-005 — every recommendation carries non-empty evidence_ref."""
        from opencontext_core.cache.base import CacheStats
        from opencontext_core.optimization import RuntimeOptimizer

        stats = CacheStats(
            entries=10,
            hits=0,
            misses=10,
            by_type={"kg_query": {"hits": 0, "misses": 10}},
        )
        opt = RuntimeOptimizer(cache_stats=stats, enabled=True, low_hit_rate_threshold=0.5)
        recs = opt.recommend()
        assert all(r.evidence_ref for r in recs)

    def test_min_samples_skips_tiny_lookups(self) -> None:
        """Below `min_samples`, the optimizer stays silent (no spurious advice)."""
        from opencontext_core.cache.base import CacheStats
        from opencontext_core.optimization import RuntimeOptimizer

        stats = CacheStats(
            entries=2,
            hits=0,
            misses=2,
            by_type={"semantic": {"hits": 0, "misses": 2}},
        )
        opt = RuntimeOptimizer(
            cache_stats=stats, enabled=True, low_hit_rate_threshold=0.5, min_samples=5
        )
        assert opt.recommend() == []

    def test_runtime_intelligence_recommendation_consumer(self) -> None:
        """`runtime_intelligence.recommendations` re-exports the optimization surface."""
        from opencontext_core.runtime_intelligence.recommendations import (
            RecommendationTarget,
            RuntimeOptimizationRecommendation,
            cache_low_hit_rate_recommendation,
        )

        rec = cache_low_hit_rate_recommendation(
            cache_type="tool_output", hit_rate=0.3, total_lookups=100
        )
        assert isinstance(rec, RuntimeOptimizationRecommendation)
        assert rec.target == RecommendationTarget.cache
        assert "tool_output" in rec.evidence_ref
        assert rec.evidence_ref != ""
