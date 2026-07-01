"""REQ-cache-v2-001 — SemanticCacheEntry + provenance round-trip."""

from __future__ import annotations


class TestSemanticEntry:
    def test_provenance_round_trip(self) -> None:
        """Provenance carries produced_by_run + content_hash; survives re-parse."""
        from opencontext_core.cache.v2.provenance import Provenance
        from opencontext_core.cache.v2.semantic import SemanticCacheEntry

        prov = Provenance(
            produced_by_run="run_abc",
            content_hash="h_xyz",
            source_refs=["src/foo.py"],
        )
        entry = SemanticCacheEntry(
            key="k1",
            value_ref="v_ref_1",
            provenance=prov,
            embedding_hash="emb_aaa",
        )
        # model_dump -> re-parse round trip
        from opencontext_core.cache.v2.semantic import SemanticCacheEntry as SCE

        data = entry.model_dump()
        rebuilt = SCE.model_validate(data)
        assert rebuilt.value_ref == "v_ref_1"
        assert rebuilt.provenance.produced_by_run == "run_abc"
        assert rebuilt.provenance.content_hash == "h_xyz"
        assert rebuilt.provenance.source_refs == ["src/foo.py"]
        assert rebuilt.embedding_hash == "emb_aaa"

    def test_key_by_embedding(self) -> None:
        """Same embedding -> same cache key (deterministic, hash-by-embedding)."""
        from opencontext_core.cache.v2.semantic import key_by_embedding

        a = key_by_embedding("hello world", producer="run_x")
        b = key_by_embedding("hello world", producer="run_x")
        c = key_by_embedding("hello world", producer="run_y")
        assert a == b
        assert a != c  # producer affects the key
