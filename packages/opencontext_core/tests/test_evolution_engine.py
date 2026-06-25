from __future__ import annotations

import types
import pytest

from opencontext_core.learning.evolution import EvolutionProposal
from opencontext_core.learning.evolution_engine import EvolutionEngine


@pytest.fixture()
def engine() -> EvolutionEngine:
    return EvolutionEngine()


def _run(omitted=None, gates=None):
    r = types.SimpleNamespace()
    r.context_omitted_paths = omitted or []
    r.gates = gates or []
    return r


def _gate(gate_id: str, status: str):
    g = types.SimpleNamespace()
    g.id = gate_id
    g.status = status
    g.message = f"{gate_id} message"
    return g


def _budget(op_type: str, confidence: float, recommended: int = 1000):
    b = types.SimpleNamespace()
    b.operation_type = op_type
    b.confidence = confidence
    b.recommended_budget = recommended
    return b


def _memory(layer: str):
    m = types.SimpleNamespace()
    m.layer = layer
    m.id = f"mem-{layer}"
    return m


class TestProposeContextWeights:
    def test_returns_proposal_when_paths_omitted(self, engine):
        run = _run(omitted=["kg/context.md", "memory/context.md"])
        proposals = engine._propose_context_weights(run, None)
        assert len(proposals) >= 1
        assert proposals[0].kind == "context_weight"

    def test_returns_empty_when_no_omitted_paths(self, engine):
        run = _run(omitted=[])
        assert engine._propose_context_weights(run, None) == []

    def test_returns_empty_when_run_result_is_none(self, engine):
        assert engine._propose_context_weights(None, None) == []

    def test_proposal_has_evidence_refs_from_omitted(self, engine):
        run = _run(omitted=["path/a.py", "path/b.py"])
        proposals = engine._propose_context_weights(run, None)
        assert "path/a.py" in proposals[0].evidence_refs

    def test_low_success_pattern_generates_proposal(self, engine):
        pattern = types.SimpleNamespace(task_type="test-apply", success_rate=0.2)
        proposals = engine._propose_context_weights(None, [pattern])
        assert any(p.kind == "context_weight" for p in proposals)

    def test_high_success_pattern_generates_no_proposal(self, engine):
        pattern = types.SimpleNamespace(task_type="test-apply", success_rate=0.9)
        assert engine._propose_context_weights(None, [pattern]) == []


class TestProposeBudgetChanges:
    @pytest.mark.parametrize("confidence,expect_proposal", [
        (0.0, False),
        (0.29, False),
        (0.30, True),
        (0.31, True),
        (1.0, True),
    ])
    def test_confidence_threshold_boundary(self, engine, confidence, expect_proposal):
        budgets = [_budget("apply", confidence)]
        proposals = engine._propose_budget_changes(budgets)
        if expect_proposal:
            assert len(proposals) == 1
            assert proposals[0].kind == "budget_profile"
        else:
            assert proposals == []

    def test_proposal_confidence_matches_budget_confidence(self, engine):
        proposals = engine._propose_budget_changes([_budget("apply", 0.75)])
        assert proposals[0].confidence == pytest.approx(0.75)

    def test_returns_empty_for_none(self, engine):
        assert engine._propose_budget_changes(None) == []

    def test_returns_empty_for_empty_list(self, engine):
        assert engine._propose_budget_changes([]) == []

    def test_multiple_budgets_above_threshold(self, engine):
        proposals = engine._propose_budget_changes([
            _budget("apply", 0.8),
            _budget("verify", 0.6),
        ])
        assert len(proposals) == 2


class TestProposeHarnessGates:
    def test_returns_proposal_for_failed_gate(self, engine):
        run = _run(gates=[_gate("failing_test_exists", "failed")])
        proposals = engine._propose_harness_gates(run)
        assert len(proposals) == 1
        assert proposals[0].kind == "harness_gate"

    def test_returns_proposal_for_warning_gate(self, engine):
        run = _run(gates=[_gate("coverage_threshold", "warning")])
        proposals = engine._propose_harness_gates(run)
        assert len(proposals) == 1

    def test_returns_empty_when_all_gates_pass(self, engine):
        run = _run(gates=[_gate("lint", "passed"), _gate("tests", "passed")])
        assert engine._propose_harness_gates(run) == []

    def test_returns_empty_when_no_gates(self, engine):
        assert engine._propose_harness_gates(_run()) == []

    def test_returns_empty_for_none_run_result(self, engine):
        assert engine._propose_harness_gates(None) == []

    def test_harness_gate_proposal_auto_applicable_is_false(self, engine):
        run = _run(gates=[_gate("failing_test_exists", "failed")])
        proposal = engine._propose_harness_gates(run)[0]
        assert proposal.auto_applicable is False

    def test_harness_gate_proposal_requires_approval(self, engine):
        run = _run(gates=[_gate("failing_test_exists", "failed")])
        proposal = engine._propose_harness_gates(run)[0]
        assert proposal.requires_approval is True

    def test_multiple_failed_gates_generate_multiple_proposals(self, engine):
        run = _run(gates=[
            _gate("lint", "failed"),
            _gate("tests", "failed"),
        ])
        proposals = engine._propose_harness_gates(run)
        assert len(proposals) == 2


class TestProposeSkillCandidates:
    def test_returns_proposal_when_3_or_more_procedural_memories(self, engine):
        memories = [_memory("PROCEDURAL")] * 3
        proposals = engine._propose_skill_candidates(memories)
        assert len(proposals) == 1
        assert proposals[0].kind == "skill_candidate"

    def test_returns_proposal_for_pattern_layer(self, engine):
        memories = [_memory("PATTERN")] * 3
        proposals = engine._propose_skill_candidates(memories)
        assert len(proposals) == 1

    def test_returns_empty_when_fewer_than_3(self, engine):
        assert engine._propose_skill_candidates([_memory("PROCEDURAL")] * 2) == []

    def test_returns_empty_for_none(self, engine):
        assert engine._propose_skill_candidates(None) == []

    def test_returns_empty_when_no_procedural_memories(self, engine):
        memories = [_memory("EPISODIC")] * 5
        assert engine._propose_skill_candidates(memories) == []

    def test_proposal_payload_has_count(self, engine):
        memories = [_memory("PROCEDURAL")] * 4
        proposal = engine._propose_skill_candidates(memories)[0]
        assert proposal.payload["procedural_memory_count"] == 4


class TestSafetyConstraint:
    def test_no_harness_gate_proposal_is_auto_applicable(self, engine):
        run = _run(gates=[
            _gate("gate-a", "failed"),
            _gate("gate-b", "warning"),
        ])
        for proposal in engine._propose_harness_gates(run):
            assert proposal.auto_applicable is False, (
                f"Proposal {proposal.proposal_id!r} has auto_applicable=True — "
                "this violates the hard constraint: gate proposals must require approval."
            )
