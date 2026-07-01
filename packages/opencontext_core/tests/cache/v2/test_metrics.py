"""REQ-cache-v2-004 — CacheMetrics hit/miss counters + CLI stats command."""

from __future__ import annotations


class TestCacheMetrics:
    def test_hit_miss_counters_increment(self) -> None:
        from opencontext_core.cache.v2.metrics import CacheMetrics

        m = CacheMetrics()
        m.record_hit("semantic")
        m.record_hit("semantic")
        m.record_miss("semantic")
        m.record_hit("tool_output")
        snap = m.snapshot()
        assert snap["semantic"]["hits"] == 2
        assert snap["semantic"]["misses"] == 1
        assert snap["tool_output"]["hits"] == 1
        assert snap["semantic"]["hit_rate"] == 2 / 3
        assert m.overall_hit_rate() == 3 / 4

    def test_cache_stats_cli_payload(self) -> None:
        """REQ-cache-v2-004 — `opencontext cache stats` payload shape."""
        from opencontext_core.cache.v2.metrics import CacheMetrics, cache_stats_payload

        m = CacheMetrics()
        for _ in range(50):
            m.record_hit("semantic")
        for _ in range(30):
            m.record_miss("tool_output")

        payload = cache_stats_payload(m)
        assert payload["hits"] == 50
        assert payload["misses"] == 30
        assert payload["hit_rate"] == 50 / 80
        assert "by_type" in payload
        assert payload["by_type"]["semantic"]["hits"] == 50
        assert payload["by_type"]["tool_output"]["misses"] == 30

    def test_event_emission(self) -> None:
        """Recording a hit/miss also fires a `cache.hit` / `cache.miss` event."""
        from opencontext_core.cache.v2.metrics import CacheMetrics

        events: list[tuple[str, str]] = []
        m = CacheMetrics(emit=lambda family, cache_type: events.append((family, cache_type)))
        m.record_hit("semantic")
        m.record_miss("ast")
        assert events == [("cache.hit", "semantic"), ("cache.miss", "ast")]
