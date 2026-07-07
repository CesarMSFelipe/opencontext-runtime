"""Tests for harness resume semantics (Phase 6 / Workstream I)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.harness.runner import HarnessRunner


def _write_events(root: Path, run_id: str, events: list[dict]) -> None:
    run_dir = root / ".opencontext" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.json").write_text(json.dumps({"events": events}), encoding="utf-8")


def test_completed_phases_empty_when_no_run(tmp_path: Path) -> None:
    runner = HarnessRunner(root=tmp_path)
    assert runner.completed_phases("ghost") == set()


def test_completed_phases_reads_passing_phases(tmp_path: Path) -> None:
    _write_events(
        tmp_path,
        "run-1",
        [
            {"index": 0, "phase": "explore", "action": "run_phase", "status": "passed"},
            {"index": 1, "phase": "apply", "action": "run_phase", "status": "warning"},
        ],
    )
    runner = HarnessRunner(root=tmp_path)
    assert runner.completed_phases("run-1") == {"explore", "apply"}


def test_completed_phases_excludes_failed(tmp_path: Path) -> None:
    _write_events(
        tmp_path,
        "run-1",
        [
            {"index": 0, "phase": "explore", "action": "run_phase", "status": "passed"},
            {"index": 1, "phase": "verify", "action": "run_phase", "status": "failed"},
        ],
    )
    runner = HarnessRunner(root=tmp_path)
    done = runner.completed_phases("run-1")
    assert "explore" in done
    assert "verify" not in done


def test_completed_phases_ignores_non_run_phase_actions(tmp_path: Path) -> None:
    _write_events(
        tmp_path,
        "run-1",
        [
            {"index": 0, "phase": "apply", "action": "skip_phase", "status": "skipped"},
            {"index": 1, "phase": "apply", "action": "pre_gate", "status": "passed"},
        ],
    )
    runner = HarnessRunner(root=tmp_path)
    assert runner.completed_phases("run-1") == set()


def test_completed_phases_handles_corrupt_events(tmp_path: Path) -> None:
    run_dir = tmp_path / ".opencontext" / "runs" / "run-x"
    run_dir.mkdir(parents=True)
    (run_dir / "events.json").write_text("{not valid json", encoding="utf-8")
    runner = HarnessRunner(root=tmp_path)
    assert runner.completed_phases("run-x") == set()


def test_resume_skips_completed_phases(tmp_path: Path) -> None:
    """A resumed run records skip events for already-completed phases."""
    # Mark the whole explore-only track's phase(s) as done in a prior run.
    runner = HarnessRunner(root=tmp_path)
    phases = runner.schedule_phases("explore-only")
    _write_events(
        tmp_path,
        "prior",
        [
            {"index": i, "phase": p, "action": "run_phase", "status": "passed"}
            for i, p in enumerate(phases)
        ],
    )

    result = runner.run("explore-only", "demo task", resume_from="prior")

    skipped = [e for e in result.events if e.action == "skip_phase"]
    skipped_phases = {e.phase for e in skipped}
    # Every previously-completed phase in this track is skipped on resume.
    assert set(phases) <= skipped_phases
    for e in skipped:
        assert e.status == "skipped"


def test_no_resume_runs_all_phases(tmp_path: Path) -> None:
    runner = HarnessRunner(root=tmp_path)
    result = runner.run("explore-only", "demo task")
    assert not any(e.action == "skip_phase" for e in result.events)


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
