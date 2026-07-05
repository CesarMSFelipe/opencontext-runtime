"""PR-008 KG v2 evidence tests — T008a.5."""

from __future__ import annotations

from opencontext_core.graph.v2.evidence import EvidenceRef, new_kg_id


class TestEvidenceRef:
    def test_evidence_round_trip(self) -> None:
        ref = EvidenceRef(source_path="src/main.py", source_line=42, source_commit="abc123")
        data = ref.model_dump(mode="json")
        assert data["source_path"] == "src/main.py"
        assert data["source_line"] == 42

    def test_new_kg_id_is_deterministic(self) -> None:
        a = new_kg_id(b"hello")
        b = new_kg_id(b"hello")
        assert a == b
        assert len(a) == 16

    def test_new_kg_id_differs_per_content(self) -> None:
        assert new_kg_id("a") != new_kg_id("b")

    def test_evidence_content_hash_auto_set(self) -> None:
        ref = EvidenceRef(source_path="x.py", source_line=1)
        assert len(ref.content_hash) == 16
