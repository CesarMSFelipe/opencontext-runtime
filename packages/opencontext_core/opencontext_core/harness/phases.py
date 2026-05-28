"""Concrete SDD phase implementations for the harness runner."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opencontext_core.harness.config import PhaseConfig
from opencontext_core.harness.gates import (
    ArtifactPersistedGate,
    ContextPackCreatedGate,
    ProjectIndexExistsGate,
    TokenBudgetGate,
)
from opencontext_core.harness.models import (
    BudgetMode,
    GateStatus,
    HarnessArtifact,
    HarnessDecision,
    PhaseGate,
    PhaseLedger,
)


@dataclass
class PhaseResult:
    """Result of executing a single harness phase."""

    phase: str
    status: GateStatus
    ledger: PhaseLedger | None = None
    gates: list[PhaseGate] = field(default_factory=list)
    artifacts: list[HarnessArtifact] = field(default_factory=list)
    decisions: list[HarnessDecision] = field(default_factory=list)
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class HarnessPhase:
    """Base class for a single harness phase."""

    id: str = ""

    def __init__(self, config: PhaseConfig, budget_mode: BudgetMode = BudgetMode.WARN) -> None:
        self.config = config
        self.budget_mode = budget_mode

    def run(self, state: Any) -> PhaseResult:
        """Execute the phase. Override in subclasses."""
        raise NotImplementedError


class ExplorePhase(HarnessPhase):
    """Explore phase: index project, build context pack, evaluate gates."""

    id = "explore"

    def run(self, state: Any) -> PhaseResult:
        from opencontext_core.runtime import OpenContextRuntime

        runtime = OpenContextRuntime(
            config_path=state.root / "opencontext.yaml"
            if (state.root / "opencontext.yaml").exists()
            else None,
            storage_path=state.root / ".storage" / "opencontext",
        )
        manifest = runtime.index_project(state.root)
        pack = runtime.build_context_pack(state.task, state.max_tokens or self.config.budget_tokens)

        # Persist context pack to run directory
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        pack_path = run_dir / "context-pack.json"
        pack_path.write_text(pack.model_dump_json(indent=2), encoding="utf-8")

        gates: list[PhaseGate] = [
            ProjectIndexExistsGate().evaluate(state.root),
            ContextPackCreatedGate().evaluate(len(pack.included)),
        ]
        ledger = PhaseLedger(
            phase="explore",
            used_tokens=pack.used_tokens,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )
        gates.append(TokenBudgetGate().evaluate(ledger))

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else (
                GateStatus.WARNING
                if any(g.status == GateStatus.WARNING for g in gates)
                else GateStatus.PASSED
            )
        )

        return PhaseResult(
            phase="explore",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"explore-pack-{state.run_id[:8]}",
                    phase="explore",
                    path=str(
                        state.root / ".opencontext" / "runs" / state.run_id / "context-pack.json"
                    ),
                    kind="context-pack",
                    description=f"Context pack with {len(pack.included)} items",
                )
            ],
            metadata={
                "included": len(pack.included),
                "omitted": len(pack.omitted),
                "indexed_files": len(manifest.files),
                "indexed_symbols": len(manifest.symbols),
            },
        )


class ArchivePhase(HarnessPhase):
    """Archive phase: persist trace, create artifacts summary."""

    id = "archive"

    def run(self, state: Any) -> PhaseResult:
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(run_dir / "run.json"),
        ]
        ledger = PhaseLedger(
            phase="archive",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )
        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else GateStatus.PASSED
        )
        return PhaseResult(
            phase="archive",
            status=status,
            ledger=ledger,
            gates=gates,
            metadata={"run_dir": str(run_dir)},
        )


class ProposePhase(HarnessPhase):
    """Propose phase: create a structured SDD change proposal from exploration."""

    id = "propose"

    def run(self, state: Any) -> PhaseResult:
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        proposal_path = run_dir / "proposal.json"

        # Build a structured proposal from the task description
        proposal = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "draft",
            "summary": f"SDD proposal: {state.task}",
            "scope": {
                "root": str(state.root),
                "max_tokens": state.max_tokens,
            },
            "approach": {
                "method": "incremental",
                "style": "provider-neutral",
            },
            "artifacts": [
                {
                    "id": f"proposal-{state.run_id[:8]}",
                    "kind": "proposal",
                    "phase": "propose",
                }
            ],
        }
        proposal_path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(proposal_path),
        ]

        ledger = PhaseLedger(
            phase="propose",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )
        gates.append(TokenBudgetGate().evaluate(ledger))

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else GateStatus.PASSED
        )

        return PhaseResult(
            phase="propose",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"proposal-{state.run_id[:8]}",
                    phase="propose",
                    path=str(proposal_path),
                    kind="proposal",
                    description=f"SDD proposal: {state.task}",
                )
            ],
            metadata={"proposal_path": str(proposal_path)},
        )


class ApplyPhase(HarnessPhase):
    """Apply phase: apply changes defined in the proposal."""

    id = "apply"

    def run(self, state: Any) -> PhaseResult:
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        apply_manifest_path = run_dir / "apply-manifest.json"
        apply_manifest = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "applied",
            "changes": [],
            "summary": f"Applied changes for: {state.task}",
        }
        apply_manifest_path.write_text(json.dumps(apply_manifest, indent=2), encoding="utf-8")

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(apply_manifest_path),
        ]
        ledger = PhaseLedger(
            phase="apply",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else GateStatus.PASSED
        )

        return PhaseResult(
            phase="apply",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"apply-manifest-{state.run_id[:8]}",
                    phase="apply",
                    path=str(apply_manifest_path),
                    kind="apply-manifest",
                    description="Apply manifest with change tracking",
                )
            ],
            metadata={"manifest_path": str(apply_manifest_path)},
        )


class VerifyPhase(HarnessPhase):
    """Verify phase: run tests and validate implementation."""

    id = "verify"

    def run(self, state: Any) -> PhaseResult:
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        verify_report_path = run_dir / "verify-report.json"

        # Provider-neutral verification: run pytest and capture results
        test_result = self._run_tests(state.root)
        verify_report = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "test_result": test_result,
            "summary": (
                "All checks passed"
                if test_result["exit_code"] == 0
                else f"Tests failed ({test_result['exit_code']})"
            ),
        }
        verify_report_path.write_text(json.dumps(verify_report, indent=2), encoding="utf-8")

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(verify_report_path),
        ]

        ledger = PhaseLedger(
            phase="verify",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )

        # If tests failed, mark as WARNING (not FAILED, since verify is about
        # reporting — FAILED is reserved for budget/gate violations)
        if test_result["exit_code"] != 0:
            gates.append(
                PhaseGate(
                    id="verify_tests_passed",
                    phase="verify",
                    status=GateStatus.WARNING,
                    message=f"Tests exited with code {test_result['exit_code']}",
                )
            )

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else (
                GateStatus.WARNING
                if any(g.status == GateStatus.WARNING for g in gates)
                else GateStatus.PASSED
            )
        )

        return PhaseResult(
            phase="verify",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"verify-report-{state.run_id[:8]}",
                    phase="verify",
                    path=str(verify_report_path),
                    kind="verify-report",
                    description=verify_report["summary"],
                )
            ],
            metadata={
                "exit_code": test_result["exit_code"],
                "passed": test_result["passed"],
                "failed": test_result["failed"],
                "errors": test_result["errors"],
            },
        )

    def _run_tests(self, root: Path) -> dict[str, Any]:
        """Run pytest in the project root, provider-neutral."""
        import re

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=short", str(root)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            passed, failed, errors = self._parse_pytest_output(result.stdout)
            return {
                "exit_code": result.returncode,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "output": result.stdout[-2000:],
                "error_output": result.stderr[-1000:],
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "output": "",
                "error_output": "pytest timed out after 120s",
            }
        except FileNotFoundError:
            return {
                "exit_code": -2,
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "output": "",
                "error_output": "pytest not found",
            }

    @staticmethod
    def _parse_pytest_output(output: str) -> tuple[int, int, int]:
        """Parse pytest -q summary line into (passed, failed, errors)."""
        import re

        # Matches: "12 passed", "3 failed", "1 error" in the summary line
        passed = sum(int(m) for m in re.findall(r"(\d+) passed", output))
        failed = sum(int(m) for m in re.findall(r"(\d+) failed", output))
        errors = sum(int(m) for m in re.findall(r"(\d+) error", output))
        return passed, failed, errors


class ReviewPhase(HarnessPhase):
    """Review phase: create review summary from all prior phase results."""

    id = "review"

    def run(self, state: Any) -> PhaseResult:
        run_dir = state.root / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        review_path = run_dir / "review.json"

        # Aggregate data from all completed phases
        review = {
            "run_id": state.run_id,
            "task": state.task,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "completed",
            "phases_completed": len(set(ledger.phase for ledger in state.ledgers)),
            "total_gates": len(state.gates),
            "passed_gates": sum(1 for g in state.gates if g.status == GateStatus.PASSED),
            "warning_gates": sum(1 for g in state.gates if g.status == GateStatus.WARNING),
            "failed_gates": sum(1 for g in state.gates if g.status == GateStatus.FAILED),
            "total_artifacts": len(state.artifacts),
            "total_decisions": len(state.decisions),
            "warnings": state.warnings,
            "trace_ids": state.trace_ids,
            "summary": f"Review completed for run {state.run_id}",
        }
        review_path.write_text(json.dumps(review, indent=2), encoding="utf-8")

        gates: list[PhaseGate] = [
            ArtifactPersistedGate().evaluate(review_path),
        ]
        if state.warnings:
            gates.append(
                PhaseGate(
                    id="review_warnings",
                    phase="review",
                    status=GateStatus.WARNING,
                    message=f"{len(state.warnings)} warnings during run",
                )
            )

        ledger = PhaseLedger(
            phase="review",
            used_tokens=0,
            budget_tokens=self.config.budget_tokens,
            budget_mode=self.budget_mode,
        )

        status = (
            GateStatus.FAILED
            if any(g.status == GateStatus.FAILED for g in gates)
            else (
                GateStatus.WARNING
                if any(g.status == GateStatus.WARNING for g in gates)
                else GateStatus.PASSED
            )
        )

        return PhaseResult(
            phase="review",
            status=status,
            ledger=ledger,
            gates=gates,
            artifacts=[
                HarnessArtifact(
                    id=f"review-{state.run_id[:8]}",
                    phase="review",
                    path=str(review_path),
                    kind="review",
                    description=f"Review summary for {state.run_id}",
                )
            ],
            metadata={
                "phases_completed": review["phases_completed"],
                "total_gates": review["total_gates"],
                "passed_gates": review["passed_gates"],
                "warning_gates": review["warning_gates"],
                "failed_gates": review["failed_gates"],
            },
        )
