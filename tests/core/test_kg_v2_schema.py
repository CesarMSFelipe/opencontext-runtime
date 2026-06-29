"""PR-008 KG v2 schema: temporal, evidence v2, mandatory-evidence rule (KG-05..07)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.models.evidence import EvidenceRef
from opencontext_core.models.kg_v2 import (
    KgEdge,
    KgEdgeType,
    KgNode,
    KgNodeType,
    TemporalMetadata,
    kg_edge_id,
    kg_node_id,
)


def test_kg_node_type_covers_book_and_is_40() -> None:
    names = {k.name for k in KgNodeType}
    for book_kind in ("DIRECTORY", "MODULE", "FUNCTION", "OWNER", "DECISION", "HARNESS"):
        assert book_kind in names
    assert len(names) >= 40


def test_kg_edge_type_covers_book_and_is_20() -> None:
    names = {k.name for k in KgEdgeType}
    for book_kind in ("CONTAINS", "DEFINES", "COVERS", "OWNS", "USED_HARNESS"):
        assert book_kind in names
    assert len(names) >= 20


def test_temporal_supersede_transition() -> None:
    tm = TemporalMetadata()
    assert tm.status == "active"
    new = tm.supersede("kg_newnode")
    assert new.status == "superseded"
    assert new.superseded_by == "kg_newnode"
    assert new.valid_to is not None
    # Original is unchanged (immutable copy).
    assert tm.status == "active"


def test_evidence_ref_v2_fields() -> None:
    ref = EvidenceRef(
        source="auth.py",
        source_type="file",
        confidence=0.8,
        source_id="run_1",
        path="src/auth.py",
        line_start=10,
        line_end=20,
        run_id="run_1",
    )
    assert ref.path == "src/auth.py"
    assert ref.line_start == 10
    assert ref.line_end == 20
    assert ref.run_id == "run_1"
    assert ref.is_kg_v2_source_type() is True


def test_evidence_ref_back_compat() -> None:
    # Pre-v2 construction (no v2 fields) still validates; "code" is not a v2 type.
    ref = EvidenceRef(source="x", source_type="code", confidence=0.5)
    assert ref.source_id is None
    assert ref.is_kg_v2_source_type() is False


def test_inferred_edge_without_evidence_rejected() -> None:
    with pytest.raises((ValidationError, ValueError)):
        KgEdge(
            id="kg_e1",
            source_id="kg_a",
            target_id="kg_b",
            type=KgEdgeType.OWNS,
            structural=False,
        )


def test_structural_edge_exempt_from_evidence() -> None:
    edge = KgEdge(
        id=kg_edge_id("kg_a", "kg_b", "contains"),
        source_id="kg_a",
        target_id="kg_b",
        type=KgEdgeType.CONTAINS,
        structural=True,
    )
    assert edge.evidence == []


def test_inferred_node_kind_requires_evidence() -> None:
    # OWNER is an inferred kind: evidence required even when structural defaulted True.
    with pytest.raises((ValidationError, ValueError)):
        KgNode(id=kg_node_id("owner", "alice"), type=KgNodeType.OWNER, name="alice")
    # With evidence it validates.
    ok = KgNode(
        id=kg_node_id("owner", "alice"),
        type=KgNodeType.OWNER,
        name="alice",
        evidence=[EvidenceRef(source="git", source_type="commit", confidence=0.7)],
    )
    assert ok.type == KgNodeType.OWNER


def test_structural_code_node_no_evidence_needed() -> None:
    node = KgNode(id=kg_node_id("function", "f", "a.py"), type=KgNodeType.FUNCTION, name="f")
    assert node.structural is True
    assert node.evidence == []


def test_kg_ids_are_content_addressed() -> None:
    a = kg_node_id("function", "f", "a.py")
    b = kg_node_id("function", "f", "a.py")
    assert a == b and a.startswith("kg_")
    assert kg_node_id("function", "g", "a.py") != a
