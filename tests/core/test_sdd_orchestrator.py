"""Tests for the SDD artifact store, DAG state, and phase result.

The legacy ``SDDOrchestrator`` class was removed for the 2.0 cut; its tests
(``TestWorkflowTracks`` / ``TestSDDOrchestrator``) went with it. The
module-level SDD graph tables it used are exercised under
``tests/harness`` and ``tests/workflows``.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.agents.artifact_store import (
    NoneStore,
    OpenSpecStore,
)
from opencontext_core.agents.dag_state import DAGState
from opencontext_core.agents.result_contract import PhaseResult


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
