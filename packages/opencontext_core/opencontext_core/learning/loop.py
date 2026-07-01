"""LearningLoop — the post-run learning orchestrator (SPEC DL-006).

After a run, the loop:

1. builds (or consumes) the per-run Decision Log and persists it as an artifact;
2. reads ``RuntimeFeedback`` from the existing ``FeedbackCollector`` substrate;
3. extracts ``LearningCandidate``s (backend: ``EvolutionEngine.propose_from_run``)
   and scores ``LearningOutcome``s;
4. produces ``ImprovementProposal``s, runs the benchmark-evidence ``PromotionGate``,
   and persists them via the existing ``EvolutionStore`` (no parallel store);
5. ROUTES memory-promotion candidates to the Memory Harness (PR-009) for governed
   promotion — it NEVER writes durable memory directly (SPEC DL-008);
6. feeds candidates/outcomes to Runtime Intelligence via the non-blocking feedback
   substrate (RI is read-only over it; doc 58 layering).

It is BEST-EFFORT and NON-BLOCKING, mirroring ``feed.record_outcome``: any
internal error is swallowed and recorded as a warning; the run's gate/status is
never changed. Every persisted field passes the no-CoT guard (SPEC DL-007).
Gated by ``learning.loop.enabled`` (default off).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.paths import StorageMode, resolve_storage_path, resolve_workspace_path
from opencontext_core.learning import candidate_extractor
from opencontext_core.learning.candidate_extractor import (
    LearningCandidate,
    LearningCandidateKind,
    LearningOutcome,
)
from opencontext_core.learning.evolution_engine import EvolutionEngine
from opencontext_core.learning.evolution_store import EvolutionStore
from opencontext_core.learning.feedback import RuntimeFeedback
from opencontext_core.learning.promotion import PromotionGate, harden_proposal
from opencontext_core.runtime.decision_log import DecisionRecorder, SelectionKind

_log = logging.getLogger("opencontext")


class LearningLoopResult(BaseModel):
    """A summary of one loop run (artifacts produced, warnings collected)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = ""
    decision_log_path: str | None = None
    candidates: int = 0
    outcomes: int = 0
    proposals_persisted: int = 0
    promotable: int = 0
    memory_candidates_routed: int = 0
    warnings: list[str] = Field(default_factory=list)


class LearningLoop:
    """Post-run learning orchestrator (non-blocking, flag-gated)."""

    def __init__(
        self,
        root: Path | str = ".",
        *,
        config: Any | None = None,
        memory_harness: Any | None = None,
        orchestrator: Any | None = None,
        benchmark_gate: Any | None = None,
    ) -> None:
        self.root = Path(root)
        self.config = config
        # Injected seams (duck-typed). Defaults keep the loop self-contained and
        # honest: no harness => promotions are emitted, never written (DL-008).
        self._memory_harness = memory_harness
        self._orchestrator = orchestrator
        self._benchmark_gate = benchmark_gate
        loop_cfg = getattr(getattr(config, "learning", None), "loop", None)
        self._feed_ri = bool(getattr(loop_cfg, "feed_runtime_intelligence", True))
        self._require_benchmark = bool(getattr(loop_cfg, "require_benchmark_evidence", True))

    def run_after(
        self,
        run_result: Any,
        *,
        decision_log: DecisionRecorder | None = None,
    ) -> LearningLoopResult:
        """Run the loop after a completed run. Never raises (DL-006)."""
        result = LearningLoopResult(run_id=str(getattr(run_result, "run_id", "") or ""))
        try:
            self._run_after(run_result, decision_log, result)
        except Exception as exc:  # outer guard — the loop must never abort a run
            self._warn(result, run_result, f"learning-loop: {exc}")
        return result

    # -- internal -----------------------------------------------------------

    def _run_after(
        self,
        run_result: Any,
        decision_log: DecisionRecorder | None,
        result: LearningLoopResult,
    ) -> None:
        # 1. Decision Log artifact (build from run decisions when none supplied).
        log = decision_log or self._build_decision_log(run_result, result)

        # 2. RuntimeFeedback from the existing substrate (read-only).
        feedback = self._read_feedback(run_result, result)

        # 3. Harvested memory records offered by the run (DL-008 candidate source).
        harvested = list(getattr(run_result, "memories_written", None) or [])

        # 4. Extract candidates (backend: EvolutionEngine.propose_from_run — DL-010).
        proposals = []
        try:
            proposals = EvolutionEngine().propose_from_run(
                run_result=run_result,
                memories_written=harvested or None,
            )
        except Exception as exc:
            self._warn(result, run_result, f"learning-loop.propose: {exc}")
        try:
            candidates = candidate_extractor.extract(
                decision_log=log,
                run_result=run_result,
                feedback=feedback,
                harvested=harvested,
                proposals=proposals,
            )
        except Exception as exc:
            self._warn(result, run_result, f"learning-loop.extract: {exc}")
            candidates = []
        result.candidates = len(candidates)

        # 5. Score outcomes.
        primary_feedback = feedback[0] if feedback else None
        outcomes = [
            candidate_extractor.score_outcome(c, run_result, primary_feedback) for c in candidates
        ]
        result.outcomes = len(outcomes)

        # 6. Benchmark-gated improvement proposals, persisted via EvolutionStore.
        self._persist_proposals(proposals, result, run_result)

        # 7. Route memory-promotion candidates to the Memory Harness (never write).
        self._route_memory_candidates(candidates, result, run_result)

        # 8. Feed candidates/outcomes to Runtime Intelligence (best-effort).
        if self._feed_ri:
            self._feed_runtime_intelligence(outcomes, run_result, result)

        # 9. Emit candidates/outcomes as a machine-readable artifact (DL-014 seam).
        self._persist_artifacts(candidates, outcomes, result, run_result)

    def _build_decision_log(self, run_result: Any, result: LearningLoopResult) -> DecisionRecorder:
        run_id = str(getattr(run_result, "run_id", "") or "")
        path = resolve_workspace_path(self.root, StorageMode.local) / "learning" / "decisions" / f"{run_id or 'run'}.jsonl"
        log = DecisionRecorder(path=path)
        try:
            for decision in list(getattr(run_result, "decisions", None) or []):
                log.record_selection(
                    decision_kind=SelectionKind.harness,
                    selected=str(getattr(decision, "phase", "") or getattr(decision, "id", "")),
                    rationale=str(getattr(decision, "rationale", "") or ""),
                    run_id=run_id,
                    evidence_refs=[t for t in [getattr(decision, "trace_id", None)] if t],
                    trace_id=getattr(decision, "trace_id", None),
                )
            result.decision_log_path = str(path)
        except Exception as exc:
            self._warn(result, run_result, f"learning-loop.decision-log: {exc}")
        return log

    def _read_feedback(self, run_result: Any, result: LearningLoopResult) -> list[RuntimeFeedback]:
        try:
            from opencontext_core.learning.feedback_collector import FeedbackCollector

            collector = FeedbackCollector(
                storage_path=resolve_storage_path(self.root, StorageMode.local) / "learning"
            )
            return [RuntimeFeedback.from_metrics(m) for m in collector.load_metrics(limit=50)]
        except Exception as exc:
            self._warn(result, run_result, f"learning-loop.feedback: {exc}")
            return []

    def _persist_proposals(
        self, proposals: list[Any], result: LearningLoopResult, run_result: Any
    ) -> None:
        if not proposals:
            return
        try:
            store = EvolutionStore(self.root)
            gate = PromotionGate(require_benchmark_evidence=self._require_benchmark)
            for proposal in proposals:
                hardened = harden_proposal(proposal)
                decision = gate.evaluate(hardened, benchmark_gate=self._benchmark_gate)
                if decision.promotable:
                    result.promotable += 1
                store.save(hardened)
                result.proposals_persisted += 1
        except Exception as exc:
            self._warn(result, run_result, f"learning-loop.persist: {exc}")

    def _route_memory_candidates(
        self, candidates: list[LearningCandidate], result: LearningLoopResult, run_result: Any
    ) -> None:
        promotions = [c for c in candidates if c.kind == LearningCandidateKind.memory_promotion]
        result.memory_candidates_routed = len(promotions)
        if not promotions or self._memory_harness is None:
            # No durable write here — the Memory Harness (PR-009) is the sole
            # governed writer (DL-008). With no harness injected we only emit.
            return
        try:
            from opencontext_core.memory_usability.memory_candidates import (
                MemoryCandidate,
                MemoryKind,
            )
            from opencontext_core.models.context import DataClassification

            for cand in promotions:
                if not cand.summary.strip():
                    continue
                self._memory_harness.promote(
                    MemoryCandidate(
                        content=cand.summary,
                        source=cand.evidence_refs[0] if cand.evidence_refs else cand.candidate_id,
                        kind=MemoryKind.FACT,
                        novelty_score=0.5,
                        reuse_likelihood=cand.confidence,
                        classification=DataClassification.INTERNAL,
                        token_cost=len(cand.summary) // 4,
                        proposed_by="learning_loop",
                        evidence_refs=[],
                        confidence=cand.confidence,
                    )
                )
        except Exception as exc:
            self._warn(result, run_result, f"learning-loop.memory-route: {exc}")

    def _feed_runtime_intelligence(
        self, outcomes: list[LearningOutcome], run_result: Any, result: LearningLoopResult
    ) -> None:
        if self._orchestrator is None:
            return
        try:
            from opencontext_core.learning.feed import record_outcome

            for outcome in outcomes:
                record_outcome(
                    self._orchestrator,
                    operation_type="learning_loop",
                    query=outcome.candidate_id,
                    success=outcome.success,
                    metadata={"run_id": outcome.run_id, **outcome.metrics},
                )
        except Exception as exc:
            self._warn(result, run_result, f"learning-loop.ri-feed: {exc}")

    def _persist_artifacts(
        self,
        candidates: list[LearningCandidate],
        outcomes: list[LearningOutcome],
        result: LearningLoopResult,
        run_result: Any,
    ) -> None:
        if not candidates and not outcomes:
            return
        try:
            run_id = result.run_id or "run"
            path = resolve_workspace_path(self.root, StorageMode.local) / "learning" / "candidates" / f"{run_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "candidates": [c.model_dump(mode="json") for c in candidates],
                        "outcomes": [o.model_dump(mode="json") for o in outcomes],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            self._warn(result, run_result, f"learning-loop.artifacts: {exc}")

    @staticmethod
    def _warn(result: LearningLoopResult, run_result: Any, message: str) -> None:
        """Record a warning without ever changing the run's gate/status (DL-006)."""
        result.warnings.append(message)
        _log.warning("%s", message)
        run_warnings = getattr(run_result, "warnings", None)
        if isinstance(run_warnings, list):
            run_warnings.append(message)


__all__ = ["LearningLoop", "LearningLoopResult"]
