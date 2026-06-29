"""SC-003 — semantic cache (conservative, disabled by default)."""

from __future__ import annotations

from opencontext_core.cache.base import CacheType, build_cache_key
from opencontext_core.cache.semantic_cache import LocalSemanticCache, SemanticCacheEntry


def _key(text: str) -> object:
    return build_cache_key(
        workflow_name="wf",
        project_hash="ph",
        model_name="m",
        prompt_version="v1",
        user_input=text,
        context="ctx",
    )


def test_semantic_entry_is_typed_cache_entry() -> None:
    entry = SemanticCacheEntry(
        key="k", key_value="k", workflow="wf", project_hash="ph", text="t", value="v"
    )
    assert entry.cache_type == CacheType.semantic
    assert entry.schema_version == "opencontext.cache_entry.v1"


def test_below_threshold_misses() -> None:
    cache = LocalSemanticCache(similarity_threshold=0.95, require_same_project_hash=False)
    cache.store(_key("the quick brown fox jumps"), "the quick brown fox jumps", "PACK")
    # A query sharing few tokens stays below threshold.
    result = cache.lookup(_key("totally different unrelated words here"), "totally different")
    assert result is None
    assert cache.stats.misses >= 1


def test_disabled_by_default_threshold_makes_distinct_queries_miss() -> None:
    # The conservative default threshold (0.92) means a non-identical task misses.
    cache = LocalSemanticCache()
    cache.store(_key("alpha beta gamma"), "alpha beta gamma", "PACK")
    assert cache.lookup(_key("delta epsilon zeta"), "delta epsilon zeta") is None
