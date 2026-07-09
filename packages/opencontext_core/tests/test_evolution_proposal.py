from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.learning.evolution import (
    EvolutionProposal,
)

_ALL_KINDS = (
    "context_weight",
    "budget_profile",
    "harness_gate",
    "skill_candidate",
    "memory_promotion",
    "kg_refresh_policy",
    "test_policy",
)

_ALL_STATUSES = ("proposed", "approved", "applied", "rejected")


def _proposal(**kwargs) -> EvolutionProposal:
    defaults = dict(
        proposal_id="test-p1",
        kind="context_weight",
        title="Test proposal",
        rationale="Testing",
    )
    return EvolutionProposal(**{**defaults, **kwargs})


class TestEvolutionProposalDefaults:
    def test_field_defaults(self):
        p = _proposal()
        assert p.status == "proposed"
        assert p.confidence == 0.5
        assert p.auto_applicable is False
        assert p.requires_approval is True
        assert p.evidence_refs == []
        assert p.payload == {}


class TestEvolutionProposalValidation:
    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            _proposal(nonexistent_field="boom")

    def test_rejects_invalid_kind(self):
        with pytest.raises(ValidationError):
            _proposal(kind="made_up_kind")

    def test_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            _proposal(status="pending_review")

    def test_requires_proposal_id(self):
        with pytest.raises((ValidationError, TypeError)):
            EvolutionProposal(kind="context_weight", title="t", rationale="r")

    def test_requires_title(self):
        with pytest.raises((ValidationError, TypeError)):
            EvolutionProposal(proposal_id="x", kind="context_weight", rationale="r")


class TestEvolutionKindLiterals:
    @pytest.mark.parametrize("kind", _ALL_KINDS)
    def test_all_kinds_valid(self, kind):
        p = _proposal(kind=kind)
        assert p.kind == kind


class TestEvolutionStatusLiterals:
    @pytest.mark.parametrize("status", _ALL_STATUSES)
    def test_all_statuses_valid(self, status):
        p = _proposal(status=status)
        assert p.status == status
