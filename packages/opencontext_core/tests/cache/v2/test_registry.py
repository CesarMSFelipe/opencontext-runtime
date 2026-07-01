"""REQ-cache-v2-001 — CacheRegistry enumerates all 7 types."""

from __future__ import annotations


class TestCacheRegistry:
    def test_seven_types_registered(self) -> None:
        """REQ-cache-v2-001 — exactly 7 cache types in canonical order."""
        from opencontext_core.cache.v2.registry import CacheRegistry

        names = CacheRegistry.list()
        assert names == [
            "semantic",
            "prompt_context",
            "tool_output",
            "ast",
            "provider_response",
            "kg_query",
            "memory_retrieval",
        ]

    def test_registry_count(self) -> None:
        from opencontext_core.cache.v2.registry import CacheRegistry

        assert CacheRegistry.count() == 7

    def test_registry_contains(self) -> None:
        from opencontext_core.cache.v2.registry import CacheRegistry

        assert CacheRegistry.contains("semantic") is True
        assert CacheRegistry.contains("memory_retrieval") is True
        assert CacheRegistry.contains("does_not_exist") is False