"""ImprovementProposal (PR-000.4 / SPEC DL-004).

Acceptance: a proposal may be *written* to the Decision Log WITHOUT
mutating its target; calling :meth:`apply` on a public/builtin proposal
without explicit human approval raises ``ApprovalRequired``; an internal
proposal with explicit approval may be marked applied (no automatic apply).
"""
from __future__ import annotations

import pytest

from opencontext_core.learning.v2.improvement_proposal import (
    ApprovalRequired,
    ImprovementProposal,
)


def _proposal(**kw) -> ImprovementProposal:
    defaults = dict(
        proposal_id="prop-1",
        title="Lower token budget",
        rationale="Use the 4k budget",
        target_type="skill_builtin",
    )
    return ImprovementProposal(**{**defaults, **kw})


class TestProposalWrite:
    def test_write_appends_to_log_without_applying(self):
        target = {"weight": 0.5}
        p = _proposal()
        log_before = {"writes": [], "applies": []}

        p.write(target=target, decision_log=log_before, applied=False)

        assert len(log_before["writes"]) == 1
        assert log_before["writes"][0]["proposal_id"] == "prop-1"
        # write() must NOT mutate target
        assert target == {"weight": 0.5}
        # and must NOT record an apply
        assert log_before["applies"] == []

    def test_write_appends_target_type_to_record(self):
        p = _proposal(target_type="skill_public")
        log: list = []
        p.write(target={"x": 1}, decision_log=log, applied=False)
        assert log[0]["target_type"] == "skill_public"


class TestProposalApply:
    def test_apply_public_proposal_without_approval_raises(self):
        p = _proposal(target_type="skill_public", approval=None)
        with pytest.raises(ApprovalRequired) as exc:
            p.apply()
        assert "human_approval_missing" in str(exc.value)

    def test_apply_builtin_proposal_without_approval_raises(self):
        p = _proposal(target_type="skill_builtin", approval=None)
        with pytest.raises(ApprovalRequired):
            p.apply()

    def test_apply_internal_proposal_with_approval_marks_applied(self):
        p = _proposal(
            target_type="internal_only",
            approval="human-1",
        )
        log: list = []
        p.apply(decision_log=log)
        assert p.status == "applied"
        assert log and log[-1]["proposal_id"] == "prop-1"
        assert log[-1]["event"] == "applied"

    def test_apply_must_never_be_called_automatically(self):
        """The proposal API surface has no auto_apply path — only explicit apply()."""
        p = _proposal()
        assert hasattr(p, "write")
        assert hasattr(p, "apply")
        assert not hasattr(p, "auto_apply")

    def test_apply_public_proposal_with_approval_marks_applied(self):
        log: list = []
        p = _proposal(target_type="skill_public", approval="ops-team")
        p.apply(decision_log=log)
        assert p.status == "applied"
        assert log[-1]["event"] == "applied"
