"""EvolutionEngine — generates propose-only evolution proposals from run evidence.

The engine reads signals from a completed run (failed context, budget patterns,
failed gates, procedural memories) and emits ``EvolutionProposal`` instances.
It NEVER mutates configuration, security settings, gates, or approval config.
"""

from __future__ import annotations

import hashlib
from typing import Any

from opencontext_core.learning.evolution import EvolutionProposal


class EvolutionEngine:
    """Produce evolution proposals from run evidence.

    All proposals are propose-only.  Gate/security/approval kinds are NEVER
    marked ``auto_applicable=True`` — they always require human review.
    """

    # Minimum confidence threshold for budget-pattern proposals.
    _BUDGET_CONFIDENCE_THRESHOLD: float = 0.3
    # Minimum procedural-memory count to trigger a memory-promotion proposal.
    _MIN_PROCEDURAL_MEMORIES: int = 3

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def propose_from_run(
        self,
        *,
        run_result: Any = None,
        learned_patterns: list[Any] | None = None,
        optimized_budgets: list[Any] | None = None,
        memories_written: list[Any] | None = None,
    ) -> list[EvolutionProposal]:
        """Generate evolution proposals from a completed run's evidence.

        Args:
            run_result: The harness ``HarnessRunResult`` (or any object with a
                ``gates`` attribute carrying ``PhaseGate`` items and a ``warnings``
                list).  May be ``None`` when called with no run context.
            learned_patterns: Patterns returned by ``PatternLearner.learn_from_history()``.
            optimized_budgets: Budget profiles returned by ``TokenOptimizer.optimize_budgets()``.
            memories_written: Memory records written during this run.

        Returns:
            List of ``EvolutionProposal`` instances (may be empty).
        """
        proposals: list[EvolutionProposal] = []

        proposals.extend(self._propose_context_weights(run_result, learned_patterns))
        proposals.extend(self._propose_budget_changes(optimized_budgets))
        proposals.extend(self._propose_harness_gates(run_result))
        proposals.extend(self._propose_skill_candidates(memories_written))

        return proposals

    # -------------------------------------------------------------------------
    # Private generators
    # -------------------------------------------------------------------------

    def _propose_context_weights(
        self,
        run_result: Any,
        learned_patterns: list[Any] | None,
    ) -> list[EvolutionProposal]:
        """Propose context-weight adjustments when context failures are recorded."""
        proposals: list[EvolutionProposal] = []

        # Signal 1: omitted context paths recorded by the runner
        omitted: list[str] = []
        if run_result is not None:
            omitted = list(getattr(run_result, "context_omitted_paths", None) or [])

        if omitted:
            pid = self._proposal_id("context_weight", ",".join(sorted(omitted[:5])))
            proposals.append(
                EvolutionProposal(
                    proposal_id=pid,
                    kind="context_weight",
                    title="Increase weight for omitted context paths",
                    rationale=(
                        f"The run omitted {len(omitted)} context path(s). "
                        "Boosting their weight may reduce future omissions."
                    ),
                    evidence_refs=omitted[:10],
                    confidence=min(0.4 + 0.05 * len(omitted), 0.9),
                    impact="low",
                    risk="low",
                    payload={"paths": omitted[:20]},
                    auto_applicable=False,
                    requires_approval=True,
                )
            )

        # Signal 2: patterns with low success rate
        if learned_patterns:
            for pattern in learned_patterns:
                success_rate = getattr(pattern, "success_rate", 1.0)
                task_type = getattr(pattern, "task_type", "unknown")
                if success_rate < 0.5:
                    pid = self._proposal_id("context_weight", f"low_success:{task_type}")
                    proposals.append(
                        EvolutionProposal(
                            proposal_id=pid,
                            kind="context_weight",
                            title=f"Adjust context weights for low-success task type: {task_type}",
                            rationale=(
                                f"Pattern '{task_type}' has success rate {success_rate:.0%}. "
                                "Refining context selection may improve outcomes."
                            ),
                            evidence_refs=[f"pattern:{task_type}"],
                            confidence=0.4,
                            impact="low",
                            risk="low",
                            payload={"task_type": task_type, "success_rate": success_rate},
                            auto_applicable=False,
                            requires_approval=True,
                        )
                    )

        return proposals

    def _propose_budget_changes(
        self,
        optimized_budgets: list[Any] | None,
    ) -> list[EvolutionProposal]:
        """Propose budget-profile changes from optimizer evidence."""
        proposals: list[EvolutionProposal] = []
        if not optimized_budgets:
            return proposals

        for budget in optimized_budgets:
            confidence = float(getattr(budget, "confidence", 0.0))
            if confidence < self._BUDGET_CONFIDENCE_THRESHOLD:
                continue
            op_type = getattr(budget, "operation_type", "unknown")
            recommended = getattr(budget, "recommended_budget", None)
            pid = self._proposal_id("budget_profile", op_type)
            proposals.append(
                EvolutionProposal(
                    proposal_id=pid,
                    kind="budget_profile",
                    title=f"Adjust token budget for operation: {op_type}",
                    rationale=(
                        f"Optimizer suggests {recommended} tokens for '{op_type}' "
                        f"with confidence {confidence:.0%}."
                    ),
                    evidence_refs=[f"budget:{op_type}"],
                    confidence=confidence,
                    impact="low",
                    risk="low",
                    payload={
                        "operation_type": op_type,
                        "recommended_budget": recommended,
                        "confidence": confidence,
                    },
                    auto_applicable=False,
                    requires_approval=True,
                )
            )

        return proposals

    def _propose_harness_gates(
        self,
        run_result: Any,
    ) -> list[EvolutionProposal]:
        """Propose gate-policy proposals for repeatedly failing gates.

        HARD CONSTRAINT: gate proposals are NEVER ``auto_applicable=True``.
        They always require human review and explicit approval.
        """
        proposals: list[EvolutionProposal] = []
        if run_result is None:
            return proposals

        gates = list(getattr(run_result, "gates", None) or [])
        failed_gates = [
            g for g in gates if str(getattr(g, "status", "")).lower() in ("failed", "warning")
        ]
        if not failed_gates:
            return proposals

        for gate in failed_gates:
            gate_id = str(getattr(gate, "id", "unknown"))
            gate_msg = str(getattr(gate, "message", ""))
            pid = self._proposal_id("harness_gate", gate_id)
            proposals.append(
                EvolutionProposal(
                    proposal_id=pid,
                    kind="harness_gate",
                    title=f"Review gate policy for: {gate_id}",
                    rationale=(
                        f"Gate '{gate_id}' did not pass in this run: {gate_msg[:200]}. "
                        "Consider adjusting thresholds or adding an exemption — "
                        "requires explicit human approval."
                    ),
                    evidence_refs=[f"gate:{gate_id}"],
                    confidence=0.5,
                    impact="medium",
                    risk="high",
                    payload={"gate_id": gate_id, "message": gate_msg},
                    # HARD CONSTRAINT: gate proposals require approval, never auto-applied.
                    auto_applicable=False,
                    requires_approval=True,
                )
            )

        return proposals

    def _propose_skill_candidates(
        self,
        memories_written: list[Any] | None,
    ) -> list[EvolutionProposal]:
        """Propose new skill candidates from procedural memory density."""
        proposals: list[EvolutionProposal] = []
        if not memories_written:
            return proposals

        procedural = [
            m
            for m in memories_written
            if str(getattr(m, "layer", "") or getattr(m, "type", "")).upper()
            in (
                "PROCEDURAL",
                "PATTERN",
            )
        ]
        if len(procedural) < self._MIN_PROCEDURAL_MEMORIES:
            return proposals

        pid = self._proposal_id("skill_candidate", f"count:{len(procedural)}")
        proposals.append(
            EvolutionProposal(
                proposal_id=pid,
                kind="skill_candidate",
                title=f"Candidate skill from {len(procedural)} procedural memories",
                rationale=(
                    f"{len(procedural)} procedural memory records written in this run. "
                    "A skill file could capture this repeated pattern durably."
                ),
                evidence_refs=[
                    f"memory:{getattr(m, 'id', i)}" for i, m in enumerate(procedural[:10])
                ],
                confidence=0.6,
                impact="medium",
                risk="low",
                payload={"procedural_memory_count": len(procedural)},
                auto_applicable=False,
                requires_approval=True,
            )
        )

        return proposals

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _proposal_id(kind: str, key: str) -> str:
        """Deterministic proposal ID — stable for the same kind+key combination."""
        return hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()[:16]


__all__ = ["EvolutionEngine"]
