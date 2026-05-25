"""Phase gate implementations for the Harness system."""

from __future__ import annotations

from pathlib import Path

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

    def evaluate(self, findings: list) -> PhaseGate:
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
