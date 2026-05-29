"""Phase gate implementations for the Harness system."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from opencontext_core.harness.models import GateStatus, PhaseGate, PhaseLedger


class ProjectIndexExistsGate:
    """Check that the project manifest exists (project was indexed)."""

    id = "project_index_exists"

    def evaluate(self, root: Path) -> PhaseGate:
        manifest = root / ".storage" / "opencontext" / "project_manifest.json"
        if manifest.exists():
            return PhaseGate(
                id=self.id,
                phase="explore",
                status=GateStatus.PASSED,
                message="Project manifest exists.",
            )
        return PhaseGate(
            id=self.id,
            phase="explore",
            status=GateStatus.FAILED,
            message="Project manifest missing — run `opencontext install` first.",
        )


class ContextPackCreatedGate:
    """Verify that a context pack was created for a given query."""

    id = "context_pack_created"

    def evaluate(self, included_count: int) -> PhaseGate:
        if included_count > 0:
            return PhaseGate(
                id=self.id,
                phase="explore",
                status=GateStatus.PASSED,
                message=f"Context pack created with {included_count} items.",
            )
        return PhaseGate(
            id=self.id,
            phase="explore",
            status=GateStatus.FAILED,
            message="Context pack is empty — try a broader query.",
        )


class TraceIdCreatedGate:
    """Check that a trace ID was generated."""

    id = "trace_id_created"

    def evaluate(self, trace_id: str | None) -> PhaseGate:
        if trace_id:
            return PhaseGate(
                id=self.id,
                phase="propose",
                status=GateStatus.PASSED,
                message=f"Trace ID created: {trace_id}",
            )
        return PhaseGate(
            id=self.id,
            phase="propose",
            status=GateStatus.FAILED,
            message="No trace ID generated.",
        )


class SecurityScanPassedGate:
    """Check that a security scan passed (no findings)."""

    id = "security_scan_passed"

    def evaluate(self, findings: list[str]) -> PhaseGate:
        if not findings:
            return PhaseGate(
                id=self.id,
                phase="verify",
                status=GateStatus.PASSED,
                message="Security scan passed — no findings.",
            )
        return PhaseGate(
            id=self.id,
            phase="verify",
            status=GateStatus.WARNING,
            message=f"Security scan found {len(findings)} item(s).",
            metadata={"finding_count": len(findings)},
        )


class TokenBudgetGate:
    """Check token budget adherence for a phase."""

    id = "token_budget"

    def evaluate(self, ledger: PhaseLedger) -> PhaseGate:
        return PhaseGate(
            id=self.id,
            phase=ledger.phase,
            status=ledger.status,
            message=ledger.message,
            metadata={
                "used_tokens": ledger.used_tokens,
                "budget_tokens": ledger.budget_tokens,
                "mode": (
                    ledger.budget_mode.value
                    if hasattr(ledger.budget_mode, "value")
                    else str(ledger.budget_mode)
                ),
            },
        )


class ArtifactPersistedGate:
    """Check that an artifact was persisted to disk."""

    id = "artifact_persisted"

    def evaluate(self, path: Path | None) -> PhaseGate:
        if path and path.exists():
            return PhaseGate(
                id=self.id,
                phase="archive",
                status=GateStatus.PASSED,
                message=f"Artifact persisted: {path}",
            )
        return PhaseGate(
            id=self.id,
            phase="archive",
            status=GateStatus.FAILED,
            message="Artifact was not persisted.",
        )


class ConfidenceGate:
    """Evaluate phase confidence based on complexity, coverage, and history.

    Produces a 0-1 score by combining:
    - Phase complexity (more complex phases need higher confidence)
    - Test coverage (from project manifest metadata)
    - Previous phase success (passed/failed prior gates)

    The gate FAILS if the combined score falls below the configured threshold.
    """

    id = "confidence"

    # Baseline complexity per phase (0.0 = trivial, 1.0 = very complex)
    _PHASE_COMPLEXITY: ClassVar[dict[str, float]] = {
        "explore": 0.2,
        "propose": 0.3,
        "spec": 0.4,
        "design": 0.5,
        "tasks": 0.3,
        "apply": 0.8,
        "verify": 0.4,
        "review": 0.3,
        "archive": 0.1,
    }

    def evaluate(
        self,
        phase: str,
        threshold: float = 0.5,
        previous_gates: list[PhaseGate] | None = None,
        test_coverage: float | None = None,
    ) -> PhaseGate:
        """Evaluate confidence for a phase.

        Args:
            phase: Phase identifier (e.g. ``"apply"``).
            threshold: Minimum confidence score required (0-1).
            previous_gates: Results from previous phases' gate evaluations.
            test_coverage: Optional test coverage ratio (0-1).

        Returns:
            A PhaseGate with PASSED or FAILED status.
        """
        score = self._calculate_score(phase, previous_gates, test_coverage)
        passed = score >= threshold

        details: list[str] = []
        details.append(f"complexity={self._PHASE_COMPLEXITY.get(phase, 0.5):.2f}")

        if previous_gates:
            prev_passed = sum(1 for g in previous_gates if g.status == GateStatus.PASSED)
            prev_total = len(previous_gates)
            details.append(f"previous={prev_passed}/{prev_total}")
        else:
            details.append("previous=no-data")

        if test_coverage is not None:
            details.append(f"coverage={test_coverage:.0%}")

        details.append(f"threshold={threshold:.2f}")
        details.append(f"score={score:.2f}")

        if passed:
            return PhaseGate(
                id=self.id,
                phase=phase,
                status=GateStatus.PASSED,
                message=f"Confidence score {score:.2f} meets threshold {threshold:.2f}.",
                metadata={"confidence_score": score, "threshold": threshold, "details": details},
            )
        return PhaseGate(
            id=self.id,
            phase=phase,
            status=GateStatus.FAILED,
            message=(
                f"Confidence score {score:.2f} below threshold {threshold:.2f}. "
                "Consider simplifying the task or increasing test coverage."
            ),
            metadata={"confidence_score": score, "threshold": threshold, "details": details},
        )

    def _calculate_score(
        self,
        phase: str,
        previous_gates: list[PhaseGate] | None = None,
        test_coverage: float | None = None,
    ) -> float:
        """Compute confidence score from weighted factors."""
        # Factor 1: Phase complexity (inverse — simpler = higher base)
        complexity = self._PHASE_COMPLEXITY.get(phase, 0.5)
        complexity_factor = 1.0 - complexity

        # Factor 2: Previous phase success rate
        prev_factor = 0.5
        if previous_gates:
            passed = sum(1 for g in previous_gates if g.status == GateStatus.PASSED)
            total = len(previous_gates)
            prev_factor = passed / max(total, 1)

        # Factor 3: Test coverage (default 0.5 when unknown)
        coverage_factor = test_coverage if test_coverage is not None else 0.5

        # Weighted combination (complexity 20%, history 50%, coverage 30%)
        return 0.2 * complexity_factor + 0.5 * prev_factor + 0.3 * coverage_factor
