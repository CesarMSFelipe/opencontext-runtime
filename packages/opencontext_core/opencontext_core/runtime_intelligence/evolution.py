"""Evolution Engine adapter + benchmark-gated promotion (book §14/§15).

This does NOT create a parallel evolution system (build-rule 3). It adapts the
book :class:`~opencontext_core.models.intelligence.EvolutionCandidate` to/from the
existing propose-only :class:`~opencontext_core.learning.evolution.EvolutionProposal`
(collision CL-009, ``alias``) so the existing
:class:`~opencontext_core.learning.evolution_store.EvolutionStore` /
:class:`~opencontext_core.learning.evolution_apply.EvolutionApplier` (approval +
rollback) stay the single source of truth. It adds the book §15 promotion gate:
promotion is denied unless required benchmarks pass and there is no first-run /
token / security regression and a rollback path exists. Evolution stays
propose-only.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.learning.evolution import EvolutionProposal
from opencontext_core.models.intelligence import BenchmarkResult, EvolutionCandidate
from opencontext_core.runtime_intelligence import events as ri_events
from opencontext_core.runtime_intelligence import telemetry_layout

# Map a legacy proposal kind to a book candidate target_type and back.
_KIND_TO_TARGET: dict[str, str] = {
    "context_weight": "context_policy",
    "budget_profile": "budget_profile",
    "harness_gate": "harness_config",
    "skill_candidate": "skill",
    "memory_promotion": "memory",
    "kg_refresh_policy": "kg_policy",
    "test_policy": "test_policy",
}
_TARGET_TO_KIND: dict[str, str] = {v: k for k, v in _KIND_TO_TARGET.items()}

# Default required benchmarks. Every promotion must clear first-run (invariant
# §23.6); security-affecting changes must also clear the security suite (§23.7).
_SECURITY_KINDS = frozenset({"harness_gate"})


def candidate_from_proposal(proposal: EvolutionProposal) -> EvolutionCandidate:
    """Adapt a legacy :class:`EvolutionProposal` into a book :class:`EvolutionCandidate`."""
    required = ["first-run"]
    if proposal.kind in _SECURITY_KINDS:
        required.append("security")
    return EvolutionCandidate(
        candidate_id=proposal.proposal_id,
        target_type=_KIND_TO_TARGET.get(proposal.kind, "skill"),
        target_id=str(proposal.payload.get("target_id", "")) if proposal.payload else "",
        change_summary=proposal.title,
        rationale=proposal.rationale,
        expected_benefit=str(proposal.payload.get("expected_benefit", ""))
        if proposal.payload
        else "",
        risks=[proposal.risk],
        generated_from_runs=list(proposal.evidence_refs),
        required_benchmarks=required,
        requires_approval=proposal.requires_approval,
    )


def proposal_from_candidate(candidate: EvolutionCandidate) -> EvolutionProposal:
    """Adapt a book :class:`EvolutionCandidate` back into a persistable proposal."""
    kind = _TARGET_TO_KIND.get(candidate.target_type, "skill_candidate")
    return EvolutionProposal(
        proposal_id=candidate.candidate_id,
        kind=kind,  # type: ignore[arg-type]
        title=candidate.change_summary or candidate.candidate_id,
        rationale=candidate.rationale,
        evidence_refs=list(candidate.generated_from_runs),
        payload={"target_id": candidate.target_id, "expected_benefit": candidate.expected_benefit},
        auto_applicable=False,
        requires_approval=candidate.requires_approval,
    )


class CandidatePromotionGate:
    """Book §15 — promotion is denied unless every evidence gate clears."""

    def __init__(self, *, token_regression_threshold: float = 0.10) -> None:
        self.token_regression_threshold = token_regression_threshold

    def can_promote(
        self,
        candidate: EvolutionCandidate,
        results: list[BenchmarkResult],
        *,
        token_baseline: dict[str, int] | None = None,
        rollback_available: bool = True,
    ) -> tuple[bool, str]:
        """Return ``(promotable, reason)``. Promotion stays propose-only/approval-gated."""
        by_suite = _index_by_suite(results)

        # 1. Required benchmarks must each be measured AND successful.
        for name in candidate.required_benchmarks:
            res = by_suite.get(name)
            if res is None or not res.measured or not res.success:
                return False, "required_benchmarks_failed"

        # 2. First-run must not regress (invariant §23.6).
        first_run = by_suite.get("first-run")
        if first_run is None or not first_run.measured or not first_run.success:
            return False, "first_run_regression"

        # 3. Token cost must not worsen beyond threshold (only checkable with a baseline).
        if token_baseline:
            for suite, baseline in token_baseline.items():
                res = by_suite.get(suite)
                if res is not None and res.measured and baseline > 0:
                    if res.tokens > baseline * (1.0 + self.token_regression_threshold):
                        return False, "token_regression"

        # 4. Security must not regress (invariant §23.7).
        for res in results:
            if res.measured and not res.security_passed:
                return False, "security_regression"

        # 5. A rollback path must exist (invariant §23.10 / book §15).
        if not rollback_available:
            return False, "no_rollback_path"

        return True, "ok"


def record_candidate(candidate: EvolutionCandidate, root: str | Path = ".") -> None:
    """Emit the candidate-created event + evolution-proposal receipt (book §16/§17)."""
    telemetry_layout.append_event(
        ri_events.EVOLUTION_CANDIDATE_CREATED,
        {"candidate_id": candidate.candidate_id, "target_type": candidate.target_type},
        root,
    )
    telemetry_layout.append_receipt(
        ri_events.RECEIPT_EVOLUTION_PROPOSAL,
        candidate.model_dump(mode="json"),
        root,
    )


def record_promotion_decision(
    candidate: EvolutionCandidate, *, promoted: bool, reason: str, root: str | Path = "."
) -> None:
    """Emit the candidate-promoted/rejected event (book §16)."""
    event = (
        ri_events.EVOLUTION_CANDIDATE_PROMOTED
        if promoted
        else ri_events.EVOLUTION_CANDIDATE_REJECTED
    )
    telemetry_layout.append_event(
        event,
        {"candidate_id": candidate.candidate_id, "reason": reason},
        root,
    )


def _index_by_suite(results: list[BenchmarkResult]) -> dict[str, BenchmarkResult]:
    """Index results by suite (preferring a measured success when duplicated)."""
    index: dict[str, BenchmarkResult] = {}
    for res in results:
        existing = index.get(res.suite)
        if existing is None or (res.measured and res.success and not existing.success):
            index[res.suite] = res
    return index


__all__ = [
    "CandidatePromotionGate",
    "candidate_from_proposal",
    "proposal_from_candidate",
    "record_candidate",
    "record_promotion_decision",
]
