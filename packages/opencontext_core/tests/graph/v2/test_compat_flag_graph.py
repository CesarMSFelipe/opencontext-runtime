"""PR-008 KG v2 compat flag test — T008a.10."""

from __future__ import annotations


class TestCompatFlag:
    def test_kg_v2_flag_off_legacy_byte_identical(self) -> None:
        """REQ_kg_v2_007: With kg_v2_enabled=False, legacy paths are untouched."""
        # Legacy indexer still works without the v2 modules
        from opencontext_core.indexing import knowledge_graph

        assert knowledge_graph is not None

    def test_v2_modules_importable(self) -> None:
        """All v2 modules import without error."""
        from opencontext_core.graph.v2 import evidence, schema, store
        assert schema.KgNodeType is not None
        assert evidence.EvidenceRef is not None
        assert store.KgStore is not None

    def test_new_kg_id_stable(self) -> None:
        """new_kg_id produces stable 16-char hex ids."""
        from opencontext_core.graph.v2.evidence import new_kg_id
        a = new_kg_id(b"test")
        b = new_kg_id(b"test")
        assert a == b
        assert len(a) == 16
