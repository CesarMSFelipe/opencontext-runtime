"""PR-000.4 benchmark-evidence promotion gate (SPEC DL-005/DL-009/DL-011)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.learning.evolution import EvolutionProposal, ImprovementProposal
from opencontext_core.learning.evolution_store import EvolutionStore
from opencontext_core.learning.promotion import PromotionGate


def _proposal(**kw) -> EvolutionProposal:
    base = dict(proposal_id="p1", kind="context_weight", title="t", rationale="r")
    base.update(kw)
    return EvolutionProposal(**base)


def test_improvement_proposal_is_evolution_proposal() -> None:
    # DL-005: no parallel model — ImprovementProposal IS EvolutionProposal.
    assert ImprovementProposal is EvolutionProposal


def test_unmeasured_proposal_blocked() -> None:
    # DL-009: empty benchmark_evidence_ref -> not promotable, reason cites it.
    decision = PromotionGate().evaluate(_proposal())
    assert decision.promotable is False
    assert "benchmark" in decision.reason.lower()


def test_measured_proposal_eligible_still_requires_approval() -> None:
    # DL-009: populated ref -> eligible, still requires_approval.
    decision = PromotionGate().evaluate(_proposal(benchmark_evidence_ref="bench:run-7"))
    assert decision.promotable is True
    assert decision.requires_approval is True


def test_persisted_via_evolution_store_round_trip(tmp_path: Path) -> None:
    # DL-011: persisted by EvolutionStore (no second store); the honesty field
    # survives the round-trip because it lives on the base model.
    store = EvolutionStore(tmp_path)
    store.save(_proposal(proposal_id="p2", benchmark_evidence_ref="bench:abc"))
    loaded = store.load("p2")
    assert loaded is not None
    assert loaded.benchmark_evidence_ref == "bench:abc"
    files = list((tmp_path / ".opencontext" / "learning" / "evolution").glob("*.json"))
    assert len(files) == 1


def test_reuses_pr011_gate_when_results_supplied() -> None:
    # The PR-011 benchmark gate is reused (duck-typed) when concrete results are
    # injected — the learning layer never imports runtime_intelligence.
    from opencontext_core.models.intelligence import BenchmarkResult
    from opencontext_core.runtime_intelligence.evolution import CandidatePromotionGate

    proposal = _proposal(benchmark_evidence_ref="bench:ok")
    passing = [
        BenchmarkResult(task_id="t", suite="first-run", measured=True, success=True),
    ]
    decision = PromotionGate().evaluate(
        proposal,
        benchmark_gate=CandidatePromotionGate(),
        benchmark_results=passing,
    )
    assert decision.promotable is True

    failing = [
        BenchmarkResult(task_id="t", suite="first-run", measured=True, success=False),
    ]
    blocked = PromotionGate().evaluate(
        proposal,
        benchmark_gate=CandidatePromotionGate(),
        benchmark_results=failing,
    )
    assert blocked.promotable is False
