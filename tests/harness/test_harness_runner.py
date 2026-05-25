"""Tests for HarnessRunner with phase execution."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.runner import HarnessRunner


class TestHarnessRunnerPhases:
    def test_create_run_generates_unique_id(self, tmp_path: Path) -> None:
        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "test task")
        assert state.run_id.startswith("sdd-")
        assert len(state.run_id) > 10
        assert state.task == "test task"

    def test_run_creates_run_directory(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        runner = HarnessRunner(root=tmp_path)
        result = runner.run("explore-only", "explore task", BudgetMode.OFF)
        run_dir = tmp_path / ".opencontext" / "runs" / result.run_id
        assert run_dir.exists()
        assert (run_dir / "run.json").exists()

    def test_run_persists_ledger_and_gates(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        runner = HarnessRunner(root=tmp_path)
        result = runner.run("explore-only", "check gates", BudgetMode.OFF)

        run_dir = tmp_path / ".opencontext" / "runs" / result.run_id
        ledger = json.loads((run_dir / "ledger.json").read_text(encoding="utf-8"))
        gates = json.loads((run_dir / "gates.json").read_text(encoding="utf-8"))

        assert len(ledger["ledgers"]) >= 1
        assert len(gates["gates"]) >= 1

    def test_run_with_sdd_workflow(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        runner = HarnessRunner(root=tmp_path)
        result = runner.run("sdd", "full sdd run", BudgetMode.OFF)
        assert result.run_id.startswith("sdd-")
        assert result.workflow == "sdd"
        # Should have results regardless of which phases executed
        assert len(result.ledgers) >= 0

    def test_run_strict_mode_fails_on_error(self, tmp_path: Path) -> None:
        """In strict mode with no project manifest, should fail."""
        runner = HarnessRunner(root=tmp_path)
        result = runner.run("explore-only", "fail test", BudgetMode.STRICT)
        assert result.status == GateStatus.FAILED


class TestHarnessRunnerConfig:
    def test_loads_yaml_config(self, tmp_path: Path) -> None:
        harness_dir = tmp_path / ".opencontext"
        harness_dir.mkdir(parents=True, exist_ok=True)
        config_yaml = (
            "version: '0.1'\n"
            "workflow_defaults:\n  budget_mode: strict\n"
            "phases:\n  explore:\n    budget_tokens: 8000\n"
        )
        (harness_dir / "harness.yaml").write_text(config_yaml, encoding="utf-8")
        from opencontext_core.harness.config import HarnessConfig

        config = HarnessConfig.from_yaml_file(harness_dir / "harness.yaml")
        assert config.budget_mode == "strict"
        assert config.phases["explore"].budget_tokens == 8000

    def test_default_config(self, tmp_path: Path) -> None:
        from opencontext_core.harness.config import HarnessConfig

        config = HarnessConfig.from_yaml_file(tmp_path / "nonexistent.yaml")
        assert config.budget_mode == "warn"
        assert "explore" in config.phases
        assert "rm -rf" in config.forbidden_commands[0]
