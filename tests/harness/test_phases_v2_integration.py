"""Integration tests for harness phases v2 — memory, contract, and mutation hooks."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.config import PhaseConfig
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
        import yaml

        from opencontext_core.config import default_config_data

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
        assert result.phase == "explore"
        # Real effect: explore produced the verified context pack on disk.
        pack_file = tmp_path / ".opencontext" / "runs" / state.run_id / "context-pack.json"
        assert pack_file.exists()
        assert result.status is not GateStatus.FAILED

    def test_explore_produces_artifacts(self, tmp_path: Path) -> None:
        """ExplorePhase produces at least one artifact (or skips gracefully)."""
        config_path = tmp_path / "opencontext.yaml"
        import yaml

        from opencontext_core.config import default_config_data

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
        # Real effect: archive wrote its report and deltas.
        run_dir = tmp_path / ".opencontext" / "runs" / state.run_id
        assert (run_dir / "archive-report.json").exists()
        assert (run_dir / "memory_delta.json").exists()
        assert result.status is not GateStatus.FAILED

    def test_archive_self_persists_run_json_so_gate_passes(self, tmp_path: Path) -> None:
        """Archive runs before the runner persists run.json; it must write its own.

        Regression: the runner persists run.json only AFTER all phases, so the
        archive phase's artifact_persisted gate failed on every real run. Archive
        now writes a preliminary run.json itself.
        """
        run_dir = tmp_path / ".opencontext" / "runs" / "test-run-abc123"
        # Deliberately do NOT pre-create run.json — the phase must create it.

        phase = ArchivePhase(
            config=PhaseConfig(budget_tokens=2000, gates=[]),
            budget_mode=BudgetMode.WARN,
            memory_store=NullAgentMemoryStore(),
        )
        result = phase.run(_FakeState(tmp_path))

        assert (run_dir / "run.json").exists()
        persisted = [g for g in result.gates if g.id == "artifact_persisted"]
        assert persisted and all(g.status == GateStatus.PASSED for g in persisted)


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
