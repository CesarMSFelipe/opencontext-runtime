"""EvolutionCandidate adapter + benchmark-gated promotion (SPEC-RI-011-16)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.learning.evolution import EvolutionProposal
from opencontext_core.learning.evolution_apply import EvolutionApplier
from opencontext_core.models.intelligence import EvolutionCandidate
from opencontext_core.runtime_intelligence.evolution import (
    CandidatePromotionGate,
    candidate_from_proposal,
    proposal_from_candidate,
)


def _candidate(required: list[str]) -> EvolutionCandidate:
    return EvolutionCandidate(
        candidate_id="cand-1",
        target_type="skill",
        change_summary="tune skill prompt",
        required_benchmarks=required,
    )


def test_adapter_round_trips_proposal_to_candidate() -> None:
    proposal = EvolutionProposal(
        proposal_id="p1",
        kind="harness_gate",
        title="review gate",
        rationale="failing gate",
    )
    candidate = candidate_from_proposal(proposal)
    assert candidate.candidate_id == "p1"
    assert "first-run" in candidate.required_benchmarks
    assert "security" in candidate.required_benchmarks  # harness_gate ⇒ security suite
    # Reverse adapter recovers a persistable proposal (no parallel store).
    back = proposal_from_candidate(candidate)
    assert back.proposal_id == "p1"
    assert back.requires_approval is True


def test_candidate_without_passing_benchmarks_is_not_promoted(bench_result) -> None:
    gate = CandidatePromotionGate()
    candidate = _candidate(["first-run"])
    # Required benchmark failed.
    ok, reason = gate.can_promote(candidate, [bench_result("first-run", success=False)])
    assert ok is False
    assert reason == "required_benchmarks_failed"


def test_absent_required_benchmark_is_not_promoted() -> None:
    gate = CandidatePromotionGate()
    candidate = _candidate(["first-run"])
    ok, reason = gate.can_promote(candidate, [])  # no results at all
    assert ok is False
    assert reason == "required_benchmarks_failed"


def test_security_regression_blocks_promotion(bench_result) -> None:
    gate = CandidatePromotionGate()
    candidate = _candidate(["first-run"])
    results = [
        bench_result("first-run", success=True),
        bench_result("security", success=True, security_passed=False),
    ]
    ok, reason = gate.can_promote(candidate, results)
    assert ok is False
    assert reason == "security_regression"


def test_missing_rollback_blocks_promotion(bench_result) -> None:
    gate = CandidatePromotionGate()
    candidate = _candidate(["first-run"])
    ok, reason = gate.can_promote(
        candidate, [bench_result("first-run", success=True)], rollback_available=False
    )
    assert ok is False
    assert reason == "no_rollback_path"


def test_token_regression_blocks_promotion(bench_result) -> None:
    gate = CandidatePromotionGate(token_regression_threshold=0.1)
    candidate = _candidate(["first-run"])
    results = [bench_result("first-run", success=True, tokens=2000)]
    ok, reason = gate.can_promote(candidate, results, token_baseline={"first-run": 1000})
    assert ok is False
    assert reason == "token_regression"


def test_clean_evidence_allows_promotion(bench_result) -> None:
    gate = CandidatePromotionGate()
    candidate = _candidate(["first-run"])
    ok, reason = gate.can_promote(candidate, [bench_result("first-run", success=True)])
    assert ok is True
    assert reason == "ok"


def test_applier_denies_promotion_when_gate_fails_and_stays_propose_only(
    tmp_path: Path, bench_result
) -> None:
    applier = EvolutionApplier(project_root=tmp_path)
    proposal = EvolutionProposal(
        proposal_id="p2",
        kind="context_weight",  # would otherwise be low-risk
        title="boost weight",
        rationale="omissions",
    )
    candidate = _candidate(["first-run"])
    result = applier.apply(
        proposal,
        approved=True,
        promotion_gate=CandidatePromotionGate(),
        benchmark_results=[bench_result("first-run", success=False)],
        candidate=candidate,
    )
    assert result.applied is False
    assert "promotion blocked" in result.reason
    assert "required_benchmarks_failed" in result.reason


def test_applier_default_behaviour_unchanged_without_gate(tmp_path: Path) -> None:
    applier = EvolutionApplier(project_root=tmp_path)
    proposal = EvolutionProposal(proposal_id="p3", kind="context_weight", title="t", rationale="r")
    # No gate supplied → existing propose-only behaviour (never auto-applies).
    result = applier.apply(proposal, approved=True)
    assert result.applied is False
