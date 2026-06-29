"""SC-013 — Runtime Optimizer (recommend-only)."""

from __future__ import annotations

from opencontext_core.cache.base import CacheStats, CacheType
from opencontext_core.cache.store import CcrBackedCacheStore
from opencontext_core.cache.tool_cache import ToolCache
from opencontext_core.optimization.optimizer import RuntimeOptimizer
from opencontext_core.optimization.recommendations import RecommendationTarget


def test_low_hit_rate_yields_cache_recommendation() -> None:
    stats = CacheStats(
        by_type={str(CacheType.tool_output): {"stored": 1, "hits": 1, "misses": 19}}
    )
    optimizer = RuntimeOptimizer(cache_stats=stats, enabled=True)
    recs = optimizer.recommend()

    assert len(recs) >= 1
    rec = recs[0]
    assert rec.target == RecommendationTarget.cache
    assert rec.rationale
    assert rec.evidence_ref


def test_disabled_optimizer_recommends_nothing() -> None:
    stats = CacheStats(by_type={"tool_output": {"hits": 0, "misses": 99}})
    assert RuntimeOptimizer(cache_stats=stats, enabled=False).recommend() == []


def test_optimizer_has_no_config_mutation_surface() -> None:
    optimizer = RuntimeOptimizer(enabled=True)
    # Recommend-only: no apply/write/mutate/save methods exist.
    forbidden = {"apply", "apply_recommendation", "write", "mutate", "save", "set_config"}
    assert forbidden.isdisjoint(set(dir(optimizer)))


def test_optimizer_does_not_mutate_provided_stats() -> None:
    stats = CacheStats(by_type={"ast": {"hits": 1, "misses": 50}})
    before = stats.model_dump()
    RuntimeOptimizer(cache_stats=stats, enabled=True).recommend()
    assert stats.model_dump() == before


def test_optimizer_reads_real_store_stats() -> None:
    store = CcrBackedCacheStore()
    cache = ToolCache(store, enabled=True)
    # Many misses, no stored value -> low hit rate.
    for i in range(6):
        cache.get("grep", {"q": i})
    optimizer = RuntimeOptimizer(cache_stats=store.stats(), enabled=True, min_samples=5)
    recs = optimizer.recommend()
    assert any(r.target == RecommendationTarget.cache for r in recs)


def test_high_hit_rate_yields_no_cache_recommendation() -> None:
    stats = CacheStats(by_type={"ast": {"hits": 49, "misses": 1}})
    recs = RuntimeOptimizer(cache_stats=stats, enabled=True).recommend()
    assert all(r.target != RecommendationTarget.cache for r in recs)
