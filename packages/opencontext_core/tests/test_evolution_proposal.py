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
    def test_status_defaults_to_proposed(self):
        assert _proposal().status == "proposed"

    def test_confidence_defaults_to_0_5(self):
        assert _proposal().confidence == 0.5

    def test_auto_applicable_defaults_to_false(self):
        assert _proposal().auto_applicable is False

    def test_requires_approval_defaults_to_true(self):
        assert _proposal().requires_approval is True

    def test_evidence_refs_defaults_to_empty_list(self):
        assert _proposal().evidence_refs == []

    def test_payload_defaults_to_empty_dict(self):
        assert _proposal().payload == {}


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
