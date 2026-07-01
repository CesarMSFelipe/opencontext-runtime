"""REQ-cache-v2-001 — KgQueryCacheEntry keyed by `kg_<hash>`."""

from __future__ import annotations


class TestKgQueryCache:
    def test_keyed_by_kg_hash(self) -> None:
        from opencontext_core.cache.v2.kg_query import KgQueryCacheEntry, kg_query_key

        k1 = kg_query_key(query="find auth bug", kg_version="kg_abc123")
        k2 = kg_query_key(query="find auth bug", kg_version="kg_abc123")
        k3 = kg_query_key(query="find auth bug", kg_version="kg_xyz999")
        assert k1 == k2
        assert k1 != k3

        e = KgQueryCacheEntry(
            key=k1,
            value_ref="v_ref_1",
            kg_version="kg_abc123",
            query_fingerprint="fp_xyz",
        )
        assert e.kg_version == "kg_abc123"
        assert e.cache_type.value == "kg_query"