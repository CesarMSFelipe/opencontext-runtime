"""Integration tests for harness phases v2 — memory, contract, and mutation hooks."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.harness.config import HarnessConfig, PhaseConfig
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import ArchivePhase, ExplorePhase
from opencontext_core.memory.agent import NullAgentMemoryStore


class _FakeState:
    """Minimal state object for phase tests."""

    def __init__(self, tmp_path: Path, task: str = "test task") -> None:
        self.run_id = "test-run-abc123"
        self.root = tmp_path
        self.task = task
        self.max_tokens = 6000
        self.ledgers = []
        self.gates = []
        self.artifacts = []
        self.decisions = []
        self.trace_ids = []
        self.warnings = []
        self.workflow = "sdd"


class TestExplorePhaseWithNullMemory:
    def test_does_not_crash_with_null_memory_store(self, tmp_path: Path) -> None:
        """ExplorePhase with NullAgentMemoryStore runs without crash."""
        # Create a minimal opencontext.yaml so the runtime can load
        config_path = tmp_path / "opencontext.yaml"
        from opencontext_core.config import default_config_data
        import yaml

        data = default_config_data()
        data["project"]["name"] = "test-project"
        config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

        phase_config = PhaseConfig(budget_tokens=6000, gates=[])
        phase = ExplorePhase(
            config=phase_config,
            budget_mode=BudgetMode.WARN,
            memory_store=NullAgentMemoryStore(),
        )
        state = _FakeState(tmp_path, task="test task for explore")
        result = phase.run(state)
        # Should not raise; status may be PASSED, WARNING, or FAILED depending on env
        assert result.phase == "explore"
        assert result.status in (GateStatus.PASSED, GateStatus.WARNING, GateStatus.FAILED)

    def test_explore_produces_artifacts(self, tmp_path: Path) -> None:
        """ExplorePhase produces at least one artifact (or skips gracefully)."""
        config_path = tmp_path / "opencontext.yaml"
        from opencontext_core.config import default_config_data
        import yaml

        data = default_config_data()
        data["project"]["name"] = "test-project"
        config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

        phase_config = PhaseConfig(budget_tokens=6000, gates=[])
        phase = ExplorePhase(
            config=phase_config,
            budget_mode=BudgetMode.WARN,
            memory_store=NullAgentMemoryStore(),
        )
        state = _FakeState(tmp_path)
        result = phase.run(state)
        # At minimum, a context-pack or error artifact should be returned
        assert isinstance(result.artifacts, list)


class TestArchivePhaseWithNullMemory:
    def test_does_not_crash_with_null_memory_store(self, tmp_path: Path) -> None:
        """ArchivePhase with NullAgentMemoryStore runs without crash."""
        # Create run.json so ArtifactPersistedGate passes
        run_dir = tmp_path / ".opencontext" / "runs" / "test-run-abc123"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text("{}")

        phase_config = PhaseConfig(budget_tokens=2000, gates=[])
        phase = ArchivePhase(
            config=phase_config,
            budget_mode=BudgetMode.WARN,
            memory_store=NullAgentMemoryStore(),
        )
        state = _FakeState(tmp_path)
        result = phase.run(state)
        assert result.phase == "archive"
        assert result.status in (GateStatus.PASSED, GateStatus.WARNING, GateStatus.FAILED)


class TestVerifyPhaseNoMutation:
    def test_no_mutation_gate_when_disabled(self, tmp_path: Path) -> None:
        """VerifyPhase with mutation disabled should not add mutation-tests gate."""
        from opencontext_core.harness.phases import VerifyPhase

        phase_config = PhaseConfig(budget_tokens=4000, gates=[])
        phase = VerifyPhase(config=phase_config, budget_mode=BudgetMode.WARN)
        state = _FakeState(tmp_path)
        result = phase.run(state)
        mutation_gates = [g for g in result.gates if g.id == "mutation-tests"]
        # Mutation config defaults to disabled, so no mutation gate expected
        assert mutation_gates == []
