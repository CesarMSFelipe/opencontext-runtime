"""HarnessRunner — orchestrates workflow execution with phase governance."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from opencontext_core.harness.budget import TokenBudgetEnforcer
from opencontext_core.harness.config import HarnessConfig
from opencontext_core.harness.models import (
    BudgetMode,
    GateStatus,
    HarnessArtifact,
    HarnessDecision,
    HarnessRunResult,
    PhaseGate,
    PhaseLedger,
)
from opencontext_core.harness.phases import (
    ApplyPhase,
    ArchivePhase,
    ExplorePhase,
    HarnessPhase,
    PhaseResult,
    ProposePhase,
    ReviewPhase,
    VerifyPhase,
)


class HarnessState:
    """Mutable state accumulated during a harness run."""

    def __init__(self, run_id: str, root: Path, task: str = "", max_tokens: int = 6000) -> None:
        self.run_id = run_id
        self.root = root
        self.task = task
        self.max_tokens = max_tokens
        self.ledgers: list[PhaseLedger] = []
        self.gates: list[PhaseGate] = []
        self.artifacts: list[HarnessArtifact] = []
        self.decisions: list[HarnessDecision] = []
        self.trace_ids: list[str] = []
        self.warnings: list[str] = []


class HarnessRunner:
    """Orchestrates workflow execution with phase governance.

    Runs SDD phases (explore → propose → apply → verify → review → archive)
    with token budget enforcement, gates, and artifact persistence.
    """

    def __init__(self, root: Path, config: HarnessConfig | None = None) -> None:
        self.root = root.resolve()
        self.config = config or HarnessConfig.from_yaml_file(root / ".opencontext" / "harness.yaml")
        self.enforcer = TokenBudgetEnforcer()

    def create_run(self, workflow: str, task: str) -> HarnessState:
        """Create a new run with a unique run_id."""
        run_id = f"{workflow}-{uuid.uuid4().hex[:12]}"
        return HarnessState(
            run_id=run_id,
            root=self.root,
            task=task,
            max_tokens=6000,
        )

    def run(
        self,
        workflow: str,
        task: str,
        budget_mode: BudgetMode = BudgetMode.WARN,
    ) -> HarnessRunResult:
        """Execute a full workflow with all phases."""
        state = self.create_run(workflow, task)
        results: list[PhaseResult] = []
        final_status = GateStatus.PASSED

        # Determine which phases to run based on workflow
        if workflow == "sdd":
            phase_ids = ["explore", "propose", "apply", "verify", "review", "archive"]
        elif workflow == "explore-only":
            phase_ids = ["explore"]
        elif workflow == "apply-only":
            phase_ids = ["apply", "verify", "archive"]
        else:
            phase_ids = ["explore", "archive"]

        for phase_id in phase_ids:
            phase_obj = self._build_phase(phase_id, budget_mode)
            if phase_obj is None:
                continue

            try:
                result = phase_obj.run(state)
            except Exception as exc:
                result = PhaseResult(
                    phase=phase_id,
                    status=GateStatus.FAILED,
                    gates=[
                        PhaseGate(
                            id=f"{phase_id}_error",
                            phase=phase_id,
                            status=GateStatus.FAILED,
                            message=f"Phase error: {exc}",
                        )
                    ],
                )
                state.warnings.append(f"{phase_id}: {exc}")

            results.append(result)
            state.ledgers.extend([result.ledger] if result.ledger else [])
            state.gates.extend(result.gates)
            state.artifacts.extend(result.artifacts)
            state.decisions.extend(result.decisions)

            if result.trace_id:
                state.trace_ids.append(result.trace_id)

            if result.status in (GateStatus.FAILED, GateStatus.WARNING):
                final_status = GateStatus.WARNING
            if result.status == GateStatus.FAILED and budget_mode is BudgetMode.STRICT:
                final_status = GateStatus.FAILED
                break

        run_result = HarnessRunResult(
            run_id=state.run_id,
            workflow=workflow,
            task=task,
            status=final_status,
            ledgers=list(state.ledgers),
            gates=list(state.gates),
            artifacts=list(state.artifacts),
            decisions=list(state.decisions),
            trace_ids=list(state.trace_ids),
            warnings=list(state.warnings),
        )

        self.persist_run(state, run_result)
        return run_result

    def _build_phase(self, phase_id: str, budget_mode: BudgetMode) -> HarnessPhase | None:
        """Build a phase instance by ID."""
        phase_config = self.config.phases.get(phase_id)
        if phase_config is None:
            return None

        if phase_id == "explore":
            return ExplorePhase(phase_config, budget_mode)
        if phase_id == "propose":
            return ProposePhase(phase_config, budget_mode)
        if phase_id == "apply":
            return ApplyPhase(phase_config, budget_mode)
        if phase_id == "verify":
            return VerifyPhase(phase_config, budget_mode)
        if phase_id == "review":
            return ReviewPhase(phase_config, budget_mode)
        if phase_id == "archive":
            return ArchivePhase(phase_config, budget_mode)

        # Fallback: return None for unknown phases
        return None

    def persist_run(self, state: HarnessState, result: HarnessRunResult) -> Path:
        """Persist run artifacts to .opencontext/runs/<run_id>/."""
        run_dir = self.root / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        def _serialize(obj: Any) -> Any:
            if hasattr(obj, "model_dump"):
                return obj.model_dump(mode="json")
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _serialize(v) for k, v in vars(obj).items()}
            if isinstance(obj, (BudgetMode, GateStatus)):
                return obj.value if hasattr(obj, "value") else str(obj)
            if isinstance(obj, list):
                return [_serialize(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            return obj

        files = {
            "run.json": {
                "run_id": result.run_id,
                "workflow": result.workflow,
                "task": result.task,
                "status": (
                    result.status.value if hasattr(result.status, "value") else str(result.status)
                ),
                "created_at": result.created_at,
            },
            "ledger.json": {"ledgers": _serialize(result.ledgers)},
            "gates.json": {"gates": _serialize(result.gates)},
            "artifacts.json": {"artifacts": _serialize(result.artifacts)},
            "decisions.json": {"decisions": _serialize(result.decisions)},
        }
        for filename, data in files.items():
            (run_dir / filename).write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8"
            )
        return run_dir
