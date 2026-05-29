"""Tests for the SDD orchestrator."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.agents.artifact_store import (
    NoneStore,
    OpenSpecStore,
)
from opencontext_core.agents.dag_state import DAGState
from opencontext_core.agents.result_contract import PhaseResult
from opencontext_core.agents.sdd_orchestrator import SDDOrchestrator
from opencontext_core.config import ArtifactStoreMode, SDDConfig


class TestArtifactStore:
    def test_openspec_store_save_and_load(self, tmp_path: Path) -> None:
        store = OpenSpecStore(root=tmp_path)
        ref = store.save("test-change", "proposal", "# Proposal\n")

        loaded = store.load("test-change", "proposal")
        assert loaded == "# Proposal\n"
        assert str(tmp_path / "changes" / "test-change" / "proposal.md") in ref

    def test_none_store(self) -> None:
        store = NoneStore()
        ref = store.save("x", "y", "z")
        assert ref == "none"
        assert store.load("x", "y") is None


class TestDAGState:
    def test_mark_completed(self) -> None:
        state = DAGState(change="test")
        state.mark_completed("explore")

        assert state.is_phase_completed("explore")
        assert state.phase == "explore"

    def test_mark_artifact_saved(self) -> None:
        state = DAGState(change="test")
        state.mark_artifact_saved("proposal")

        assert state.is_artifact_saved("proposal")

    def test_save_and_recover(self) -> None:
        state = DAGState(change="my-change")
        state.mark_completed("explore")
        state.mark_completed("propose")
        state.mark_artifact_saved("proposal")

        content = state.save()
        recovered = DAGState.recover(content)

        assert recovered is not None
        assert recovered.change == "my-change"
        assert recovered.is_phase_completed("explore")
        assert recovered.is_phase_completed("propose")
        assert recovered.is_artifact_saved("proposal")

    def test_recover_invalid_returns_none(self) -> None:
        assert DAGState.recover("") is None
        assert DAGState.recover("not yaml") is None


class TestPhaseResult:
    def test_success(self) -> None:
        result = PhaseResult(status="success")
        assert result.is_success()
        assert not result.is_blocked()

    def test_blocked(self) -> None:
        result = PhaseResult(status="blocked")
        assert not result.is_success()
        assert result.is_blocked()

    def test_to_from_dict(self) -> None:
        result = PhaseResult(
            status="success",
            executive_summary="Done",
            artifacts=["path/to/artifact"],
        )
        data = result.to_dict()
        restored = PhaseResult.from_dict(data)
        assert restored.status == "success"
        assert restored.executive_summary == "Done"

    def test_warnings_field(self) -> None:
        """Warnings field serialization round-trip."""
        result = PhaseResult(status="success", warnings=["spec missing non_goals"])
        data = result.to_dict()
        assert "warnings" in data
        assert data["warnings"] == ["spec missing non_goals"]

        restored = PhaseResult.from_dict(data)
        assert restored.warnings == ["spec missing non_goals"]

    def test_warnings_default_empty(self) -> None:
        """Default warnings is empty list."""
        result = PhaseResult()
        assert result.warnings == []

        data = result.to_dict()
        restored = PhaseResult.from_dict(data)
        assert restored.warnings == []

    def test_warnings_backward_compat(self) -> None:
        """Old dict without warnings key still loads."""
        data = {
            "status": "success",
            "executive_summary": "",
            "detailed_report": "",
            "artifacts": [],
            "next_recommended": "none",
            "risks": [],
            "skill_resolution": "none",
        }
        restored = PhaseResult.from_dict(data)
        assert restored.warnings == []


class TestWorkflowTracks:
    """Test workflow track support."""

    def test_quick_track_three_phases(self, tmp_path: Path) -> None:
        config = SDDConfig(
            artifact_store={"mode": "openspec", "openspec": {"path": str(tmp_path)}}, track="quick"
        )
        orch = SDDOrchestrator(config=config)
        orch.start_change("test")
        assert orch._track == "quick"

        # Quick track: explore -> apply -> verify
        assert orch.get_next_phases() == ["explore"]
        orch.run_phase("explore", "# Explore\n")
        assert "apply" in orch.get_next_phases()
        assert "spec" not in orch.get_next_phases()  # not in quick track
        orch.run_phase("apply", "# Apply\n")
        orch.run_phase("verify", "# Verify\n")
        assert orch.is_complete()

    def test_standard_track_five_phases(self, tmp_path: Path) -> None:
        config = SDDConfig(
            artifact_store={"mode": "openspec", "openspec": {"path": str(tmp_path)}},
            track="standard",
        )
        orch = SDDOrchestrator(config=config)
        orch.start_change("test")

        assert orch._track == "standard"
        phases = ["explore", "spec", "design", "apply", "verify"]
        for phase in phases:
            orch.run_phase(phase, f"# {phase}\n")
        assert orch.is_complete()

    def test_full_track_eight_phases(self, tmp_path: Path) -> None:
        config = SDDConfig(
            artifact_store={"mode": "openspec", "openspec": {"path": str(tmp_path)}}, track="full"
        )
        orch = SDDOrchestrator(config=config)
        orch.start_change("test")

        for phase in [
            "explore",
            "propose",
            "spec",
            "design",
            "tasks",
            "apply",
            "verify",
            "archive",
        ]:
            orch.run_phase(phase, f"# {phase}\n")
        assert orch.is_complete()

    def test_invalid_phase_rejected(self, tmp_path: Path) -> None:
        config = SDDConfig(
            artifact_store={"mode": "openspec", "openspec": {"path": str(tmp_path)}}, track="quick"
        )
        orch = SDDOrchestrator(config=config)
        orch.start_change("test")
        orch.run_phase("explore", "# Explore\n")

        # propose is not in quick track
        result = orch.run_phase("propose", "# Propose\n")
        assert result.is_blocked()
        assert "not in the active track" in result.executive_summary

    def test_full_track_regression(self, tmp_path: Path) -> None:
        """Pre-existing orchestrator tests pass with full track."""
        config = SDDConfig(artifact_store={"mode": "openspec", "openspec": {"path": str(tmp_path)}})
        orch = SDDOrchestrator(config=config)
        orch.start_change("test")

        assert not orch.is_complete()
        for phase in [
            "explore",
            "propose",
            "spec",
            "design",
            "tasks",
            "apply",
            "verify",
            "archive",
        ]:
            orch.run_phase(phase, f"# {phase}\n")
        assert orch.is_complete()


class TestSDDOrchestrator:
    def test_start_change(self) -> None:
        orch = SDDOrchestrator()
        state = orch.start_change("my-change")

        assert state.change == "my-change"
        assert orch.get_state() is state

    def test_can_run_phase_no_deps(self) -> None:
        orch = SDDOrchestrator()
        orch.start_change("test")

        assert orch.can_run_phase("explore")

    def test_can_run_phase_with_deps(self) -> None:
        orch = SDDOrchestrator()
        orch.start_change("test")

        assert not orch.can_run_phase("propose")

        orch.state.mark_completed("explore")  # type: ignore[union-attr]
        assert orch.can_run_phase("propose")

    def test_run_phase_success(self, tmp_path: Path) -> None:
        config = SDDConfig(artifact_store={"mode": "openspec", "openspec": {"path": str(tmp_path)}})
        orch = SDDOrchestrator(config=config)
        orch.start_change("test-change")

        result = orch.run_phase("explore", "# Exploration\n")

        assert result.is_success()
        assert "explore" in result.executive_summary
        assert orch.state.is_phase_completed("explore")  # type: ignore[union-attr]

    def test_run_phase_blocked(self) -> None:
        orch = SDDOrchestrator()
        orch.start_change("test")

        result = orch.run_phase("propose", "# Proposal\n")

        assert result.is_blocked()
        assert "Dependencies" in result.executive_summary

    def test_is_complete(self, tmp_path: Path) -> None:
        config = SDDConfig(artifact_store={"mode": "openspec", "openspec": {"path": str(tmp_path)}})
        orch = SDDOrchestrator(config=config)
        orch.start_change("test")

        assert not orch.is_complete()

        for phase in [
            "explore",
            "propose",
            "spec",
            "design",
            "tasks",
            "apply",
            "verify",
            "archive",
        ]:
            orch.run_phase(phase, f"# {phase}\n")

        assert orch.is_complete()

    def test_get_next_phases(self, tmp_path: Path) -> None:
        config = SDDConfig(artifact_store={"mode": "openspec", "openspec": {"path": str(tmp_path)}})
        orch = SDDOrchestrator(config=config)
        orch.start_change("test")

        # Initially only explore is ready
        assert orch.get_next_phases() == ["explore"]

        orch.run_phase("explore", "# Explore\n")
        # After explore, propose is ready
        assert "propose" in orch.get_next_phases()

    def test_config_modes(self) -> None:
        for mode in [ArtifactStoreMode.NONE, ArtifactStoreMode.ENGRAM]:
            config = SDDConfig(artifact_store={"mode": mode.value})
            orch = SDDOrchestrator(config=config)
            assert orch.store is not None
