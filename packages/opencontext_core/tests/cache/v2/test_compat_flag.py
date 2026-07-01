"""REQ-cache-v2-compat-flag — `cache.runtime.enabled=False` legacy byte-identical (PR-000.3)."""

from __future__ import annotations


class TestCacheCompatFlag:
    def test_runtime_cache_flag_default_off(self) -> None:
        from opencontext_core.config import RuntimeCacheConfig

        cfg = RuntimeCacheConfig()
        assert cfg.enabled is False
        assert cfg.optimizer_enabled is False

    def test_cache_v2_modules_importable_with_flag_off(self) -> None:
        """The v2 layer must import cleanly even when the runtime flag is off."""
        from opencontext_core.cache.v2 import (
            CacheEntry,
            CacheRegistry,
            CacheStrategy,
            CacheType,
            SemanticCache,
        )

        assert CacheRegistry.count() == 7
        assert CacheType.semantic.value == "semantic"
        c = SemanticCache(CacheStrategy.TTL, max_entries=4)
        c.set("k", 42)
        assert c.get("k") == 42
        assert isinstance(CacheEntry, type)

    def test_leaf_guard_clean(self) -> None:
        """The leaf-guard walk exits 0 on the shipped cache/v2/ tree."""
        from opencontext_core.cache.v2.leaf_guard import verify_no_upward_imports

        assert verify_no_upward_imports() == []