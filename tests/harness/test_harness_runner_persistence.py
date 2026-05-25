"""Tests for HarnessRunner persistence and _sdd_flow wiring."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.models import (
    BudgetMode,
    GateStatus,
    HarnessArtifact,
    HarnessRunResult,
    PhaseGate,
    PhaseLedger,
)
from opencontext_core.harness.runner import HarnessRunner


class TestHarnessRunnerPersistence:
    def test_persist_run_creates_directory(self, tmp_path: Path) -> None:
        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "test task")
        result = HarnessRunResult(
            run_id=state.run_id,
            workflow="sdd",
            task="test task",
            status=GateStatus.PASSED,
        )
        run_dir = runner.persist_run(state, result)
        assert run_dir.exists()
        assert run_dir.name == state.run_id

    def test_persist_run_creates_json_files(self, tmp_path: Path) -> None:
        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "test task")
        result = HarnessRunResult(
            run_id=state.run_id,
            workflow="sdd",
            task="test task",
            status=GateStatus.PASSED,
            ledgers=[
                PhaseLedger(
                    phase="explore",
                    used_tokens=3000,
                    budget_tokens=6000,
                    budget_mode=BudgetMode.WARN,
                )
            ],
            gates=[
                PhaseGate(
                    id="project_index_exists",
                    phase="explore",
                    status=GateStatus.PASSED,
                    message="OK",
                )
            ],
        )
        run_dir = runner.persist_run(state, result)

        assert (run_dir / "run.json").exists()
        assert (run_dir / "ledger.json").exists()
        assert (run_dir / "gates.json").exists()
        assert (run_dir / "artifacts.json").exists()
        assert (run_dir / "decisions.json").exists()

    def test_persist_run_content(self, tmp_path: Path) -> None:
        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "auth task")
        result = HarnessRunResult(
            run_id=state.run_id,
            workflow="sdd",
            task="auth task",
            status=GateStatus.PASSED,
            trace_ids=["trace-1"],
            artifacts=[
                HarnessArtifact(
                    id="a1",
                    phase="explore",
                    path="/tmp/pack.json",
                    kind="context-pack",
                )
            ],
        )
        run_dir = runner.persist_run(state, result)

        run_data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        assert run_data["run_id"] == state.run_id
        assert run_data["workflow"] == "sdd"
        assert run_data["task"] == "auth task"
        assert run_data["status"] == "passed"

        artifacts_data = json.loads((run_dir / "artifacts.json").read_text(encoding="utf-8"))
        assert len(artifacts_data["artifacts"]) == 1
        assert artifacts_data["artifacts"][0]["id"] == "a1"

    def test_multiple_runs_get_unique_dirs(self, tmp_path: Path) -> None:
        runner = HarnessRunner(root=tmp_path)
        state1 = runner.create_run("sdd", "task1")
        state2 = runner.create_run("sdd", "task2")
        r1 = HarnessRunResult(
            run_id=state1.run_id,
            workflow="sdd",
            task="task1",
            status=GateStatus.PASSED,
        )
        r2 = HarnessRunResult(
            run_id=state2.run_id,
            workflow="sdd",
            task="task2",
            status=GateStatus.PASSED,
        )
        dir1 = runner.persist_run(state1, r1)
        dir2 = runner.persist_run(state2, r2)
        assert dir1 != dir2
        assert dir1.parent == dir2.parent
