"""PR-009 SPEC-MEM-009-08: MemoryCandidate book fields (proposer/evidence/reuse/confidence)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.memory_usability.memory_candidates import MemoryCandidate, MemoryKind
from opencontext_core.models.context import DataClassification
from opencontext_core.models.evidence import EvidenceRef


def _candidate(**kw: object) -> MemoryCandidate:
    base: dict[str, object] = dict(
        content="Tokens must be refreshed hourly for the gateway.",
        source="trace:abc",
        kind=MemoryKind.FACT,
        novelty_score=0.7,
        reuse_likelihood=0.7,
        classification=DataClassification.INTERNAL,
        token_cost=20,
    )
    base.update(kw)
    return MemoryCandidate(**base)  # type: ignore[arg-type]


def test_candidate_book_fields_default() -> None:
    candidate = _candidate()
    assert candidate.proposed_by == ""
    assert candidate.evidence_refs == []
    assert candidate.expected_reuse == ""
    assert candidate.confidence == 0.0


def test_evidence_less_candidate_is_structurally_flagged() -> None:
    candidate = _candidate()
    # The promotion gate can reject on this empty list.
    assert candidate.evidence_refs == []


def test_candidate_carries_provenance_when_supplied() -> None:
    candidate = _candidate(
        proposed_by="explorer",
        evidence_refs=[EvidenceRef(source="auth.py", source_type="file", confidence=0.9)],
        expected_reuse="recall on auth tasks",
        confidence=0.8,
    )
    assert candidate.proposed_by == "explorer"
    assert len(candidate.evidence_refs) == 1
    assert candidate.confidence == 0.8


def test_extra_fields_still_forbidden() -> None:
    with pytest.raises(ValidationError):
        _candidate(not_a_real_field=True)
