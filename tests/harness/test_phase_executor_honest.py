"""Honest executor-reporting contract for the work-producing planning phases.

Task 7.7: SpecPhase / DesignPhase / TasksPhase MUST NOT present a static
template scaffold as a successful AI-produced artifact. They must EITHER:

  - invoke the real executor (the now-callable ``SubAgentDelegate``) when one is
    wired, record its output and ``metadata["executor"] == "real"``, and report
    ``status == GateStatus.PASSED``, OR
  - when no executor / LLM is available, report a non-PASSED status
    (executor-absent), persist the template clearly marked as a *scaffold*
    (manifest status ``"planned"``, ``metadata["executor"] == "absent"``), and
    NOT label it ``"completed"`` / success.

This mirrors the honest-ApplyPhase contract already enforced in this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opencontext_core.agents.delegation import DelegationMode, SubAgentDelegate
from opencontext_core.harness.config import PhaseConfig
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import (
    DesignPhase,
    PhaseResult,
    SpecPhase,
    TasksPhase,
)
from opencontext_core.harness.runner import HarnessRunner, HarnessState


def _seed_upstream(run_dir: Path) -> None:
    """Create the upstream artifacts each planning phase reads from disk."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "proposal.json").write_text(
        json.dumps({"task": "seed task", "approach": {"method": "incremental"}}),
        encoding="utf-8",
    )
    (run_dir / "spec.md").write_text(
        "# Spec\n\n### Requirement: Seed\nMUST do the thing.\n",
        encoding="utf-8",
    )
    (run_dir / "design.md").write_text(
        "# Design\n\n## Files to Create/Modify\n\n- src/seed.py\n",
        encoding="utf-8",
    )


def _make_state(tmp_path: Path) -> HarnessState:
    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", "seed task")
    state.root = tmp_path
    _seed_upstream(tmp_path / ".opencontext" / "runs" / state.run_id)
    return state


def _cfg(tmp_path: Path, phase: str) -> PhaseConfig:
    cfg = HarnessRunner(root=tmp_path).config.phases.get(phase)
    assert cfg is not None
    return cfg


def _read_manifest(result: PhaseResult) -> dict[str, Any]:
    """Read the phase's honest manifest side-car.

    The phase persists a manifest next to the artifact so the manifest
    ``status``/``executor`` can be inspected even when the artifact body is
    markdown. The side-car path is recorded in ``metadata["manifest_path"]``.
    """
    manifest_path = Path(result.metadata["manifest_path"])
    data: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return data


# --------------------------------------------------------------------------
# No executor wired → honest "planned"/executor-absent, never completed.
# --------------------------------------------------------------------------


class TestPlanningPhasesAbsentExecutor:
    def test_spec_without_executor_is_not_completed(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        result = SpecPhase(_cfg(tmp_path, "spec"), BudgetMode.OFF).run(state)

        # PhaseResult status is NOT PASSED — a scaffold is not a success.
        assert result.status != GateStatus.PASSED
        assert result.metadata.get("executor") == "absent"
        manifest = _read_manifest(result)
        assert manifest["status"] == "planned"
        assert manifest["status"] != "completed"
        # The scaffold body is clearly marked as a scaffold, not an AI artifact.
        body = Path(result.artifacts[0].path).read_text(encoding="utf-8")
        assert "scaffold" in body.lower()

    def test_design_without_executor_is_not_completed(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        result = DesignPhase(_cfg(tmp_path, "design"), BudgetMode.OFF).run(state)

        assert result.status != GateStatus.PASSED
        assert result.metadata.get("executor") == "absent"
        manifest = _read_manifest(result)
        assert manifest["status"] == "planned"

    def test_tasks_without_executor_is_not_completed(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        result = TasksPhase(_cfg(tmp_path, "tasks"), BudgetMode.OFF).run(state)

        assert result.status != GateStatus.PASSED
        assert result.metadata.get("executor") == "absent"
        manifest = _read_manifest(result)
        assert manifest["status"] == "planned"

    def test_tasks_scaffold_uses_task_files_not_internal_paths(self, tmp_path: Path) -> None:
        # Regression: when the design scaffold lists no files, the fallback used to
        # hard-code OpenContext's own paths (harness/gates.py) into every project's
        # task plan. It must use the files explore surfaced for THIS task instead.
        state = _make_state(tmp_path)
        run_dir = tmp_path / ".opencontext" / "runs" / state.run_id
        (run_dir / "design.md").write_text("# Design\n\nNo files listed.\n", encoding="utf-8")
        state.context_required_sources = ["src/cart.py"]

        result = TasksPhase(_cfg(tmp_path, "tasks"), BudgetMode.OFF).run(state)
        tasks = json.loads(Path(result.artifacts[0].path).read_text(encoding="utf-8"))
        all_paths = [p for t in tasks["tasks"] for p in t["file_paths"]]
        assert "src/cart.py" in all_paths
        assert not any("harness/gates" in p for p in all_paths)

    def test_artifact_still_persisted_when_absent(self, tmp_path: Path) -> None:
        """Persistence behavior is unchanged — the scaffold is still written."""
        state = _make_state(tmp_path)
        result = SpecPhase(_cfg(tmp_path, "spec"), BudgetMode.OFF).run(state)
        assert Path(result.artifacts[0].path).exists()
        assert result.artifacts[0].kind == "spec"


# --------------------------------------------------------------------------
# Real executor wired → the phase runs it and records executor="real".
# --------------------------------------------------------------------------


def _recording_delegate(calls: list[str]) -> SubAgentDelegate:
    delegate = SubAgentDelegate(mode=DelegationMode.LOCAL)
    for phase in ("spec", "design", "tasks"):

        def _handler(ctx: dict[str, Any], _p: str = phase) -> dict[str, Any]:
            calls.append(_p)
            return {
                "status": "success",
                "output": f"REAL {_p} OUTPUT for {ctx.get('task')}",
            }

        delegate.register_handler(phase, _handler)
    return delegate


def _attach_delegate(state: Any, delegate: SubAgentDelegate) -> None:
    """Attach a delegation layer to the run state.

    The executor/delegation layer is supplied on the state (mirroring how
    ``state.apply_edits`` is supplied to ApplyPhase). Typed as ``Any`` so the
    optional, runner-owned attribute does not require a HarnessState change.
    """
    state.delegate = delegate


class TestPlanningPhasesRealExecutor:
    def test_spec_runs_real_executor(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        calls: list[str] = []
        _attach_delegate(state, _recording_delegate(calls))

        result = SpecPhase(_cfg(tmp_path, "spec"), BudgetMode.OFF).run(state)

        assert "spec" in calls, "spec phase must call the delegation layer"
        assert result.status == GateStatus.PASSED
        assert result.metadata.get("executor") == "real"
        manifest = _read_manifest(result)
        assert manifest["status"] == "completed"
        # The executor's real output is what landed in the artifact.
        body = Path(result.artifacts[0].path).read_text(encoding="utf-8")
        assert "REAL spec OUTPUT" in body

    def test_design_runs_real_executor(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        calls: list[str] = []
        _attach_delegate(state, _recording_delegate(calls))

        result = DesignPhase(_cfg(tmp_path, "design"), BudgetMode.OFF).run(state)

        assert "design" in calls
        assert result.status == GateStatus.PASSED
        assert result.metadata.get("executor") == "real"
        body = Path(result.artifacts[0].path).read_text(encoding="utf-8")
        assert "REAL design OUTPUT" in body

    def test_tasks_runs_real_executor(self, tmp_path: Path) -> None:
        state = _make_state(tmp_path)
        calls: list[str] = []
        _attach_delegate(state, _recording_delegate(calls))

        result = TasksPhase(_cfg(tmp_path, "tasks"), BudgetMode.OFF).run(state)

        assert "tasks" in calls
        assert result.status == GateStatus.PASSED
        assert result.metadata.get("executor") == "real"
        body = Path(result.artifacts[0].path).read_text(encoding="utf-8")
        assert "REAL tasks OUTPUT" in body

    def test_executor_error_is_reported_not_faked(self, tmp_path: Path) -> None:
        """A failing executor is surfaced, never silently downgraded to a stub."""
        state = _make_state(tmp_path)

        delegate = SubAgentDelegate(mode=DelegationMode.LOCAL)

        def _boom(ctx: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("executor exploded")

        delegate.register_handler("spec", _boom)
        _attach_delegate(state, delegate)

        result = SpecPhase(_cfg(tmp_path, "spec"), BudgetMode.OFF).run(state)
        # An executor that errored is NOT a success.
        assert result.status != GateStatus.PASSED
        manifest = _read_manifest(result)
        assert manifest["status"] != "completed"
