"""REQ-05: mark_done with missing required_artifacts → status=blocked."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.workflow.phase_result import PhaseResultEnvelope


def _write_envelope(
    run_dir: Path,
    run_id: str,
    change_id: str,
    phase_name: str,
    artifacts: list[str] | None = None,
    status: str = "passed",
) -> None:
    envelope = PhaseResultEnvelope(
        run_id=run_id,
        change_id=change_id,
        phase=phase_name,
        status=status,
        duration_s=0.0,
        artifacts=artifacts or [],
    )
    (run_dir / f"phase-result.{phase_name}.json").write_text(
        envelope.model_dump_json(), encoding="utf-8"
    )


def test_mark_done_blocked_when_declared_artifact_missing(tmp_path: Path) -> None:
    """Envelope declares artifacts=[...] but file missing on disk → status=blocked."""
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Test declared artifact integrity")

    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write the explore envelope declaring a nonexistent artifact.
    nonexistent = "nonexistent.json"
    _write_envelope(
        run_dir,
        state.identity.run_id,
        state.identity.change_id,
        "explore",
        artifacts=[nonexistent],
        status="passed",
    )
    # NOTE: Do NOT create nonexistent.json on disk.
    assert not (run_dir / nonexistent).exists()

    state = conductor.mark_done(state.identity.run_id, "explore")

    explore_phase = state.phase("explore")  # type: ignore[arg-type]
    assert explore_phase.status == "blocked", f"Expected status=blocked, got {explore_phase.status}"
    warnings = explore_phase.warnings or []
    assert any(nonexistent in w for w in warnings), (
        f"Expected warning mentioning '{nonexistent}', got: {warnings}"
    )
    assert state.blocked_reason is not None
    assert nonexistent in state.blocked_reason


def test_mark_done_passes_when_declared_artifacts_present(tmp_path: Path) -> None:
    """Envelope declares artifacts=[...] and files exist on disk → status=passed."""
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Test declared artifact integrity OK")

    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    declared = "explore.artifact.json"
    # Create the declared artifact on disk.
    (run_dir / declared).write_text("{}", encoding="utf-8")

    _write_envelope(
        run_dir,
        state.identity.run_id,
        state.identity.change_id,
        "explore",
        artifacts=[declared],
        status="passed",
    )

    state = conductor.mark_done(state.identity.run_id, "explore")

    explore_phase = state.phase("explore")  # type: ignore[arg-type]
    assert explore_phase.status == "passed", f"Expected status=passed, got {explore_phase.status}"


def test_mark_done_blocked_when_required_artifact_missing(tmp_path: Path) -> None:
    """Marking 'propose' done without explore.artifact.json on disk → status=blocked."""
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Test artifact integrity")

    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Complete explore first (no required_artifacts, so no blocking).
    explore_artifacts = ["explore.artifact.json"]
    for a in explore_artifacts:
        (run_dir / a).write_text("{}", encoding="utf-8")
    _write_envelope(
        run_dir,
        state.identity.run_id,
        state.identity.change_id,
        "explore",
        artifacts=explore_artifacts,
    )
    state = conductor.mark_done(state.identity.run_id, "explore")

    # Now try to mark 'propose' done — but DON'T write explore.artifact.json
    # NOTE: propose requires explore.artifact.json in its required_artifacts.
    # We delete it to simulate missing artifact.
    (run_dir / "explore.artifact.json").unlink()

    _write_envelope(
        run_dir,
        state.identity.run_id,
        state.identity.change_id,
        "propose",
        artifacts=[],
    )

    # propose.required_artifacts = ["explore.artifact.json"] — file now missing
    state = conductor.mark_done(state.identity.run_id, "propose")

    # The propose phase should be blocked (not passed).
    propose_phase = state.phase("propose")  # type: ignore[arg-type]
    assert propose_phase.status == "blocked"
    assert state.blocked_reason is not None
    assert "explore.artifact.json" in state.blocked_reason
    # Warning should name the missing artifact.
    warnings = propose_phase.warnings or []
    assert any("explore.artifact.json" in w for w in warnings), (
        f"Expected warning mentioning explore.artifact.json, got: {warnings}"
    )


def test_mark_done_passes_when_required_artifacts_present(tmp_path: Path) -> None:
    """Marking 'propose' done WITH explore.artifact.json present → status=passed."""
    conductor = OcNewConductor(tmp_path)
    state = conductor.start("Test artifact integrity OK")

    run_dir = tmp_path / ".opencontext" / "runs" / state.identity.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Mark explore done.
    explore_artifacts = ["explore.artifact.json"]
    for a in explore_artifacts:
        (run_dir / a).write_text("{}", encoding="utf-8")
    _write_envelope(
        run_dir,
        state.identity.run_id,
        state.identity.change_id,
        "explore",
        artifacts=explore_artifacts,
    )
    state = conductor.mark_done(state.identity.run_id, "explore")

    # Ensure explore.artifact.json still exists (required by propose).
    assert (run_dir / "explore.artifact.json").exists()

    _write_envelope(
        run_dir,
        state.identity.run_id,
        state.identity.change_id,
        "propose",
        artifacts=[],
    )
    state = conductor.mark_done(state.identity.run_id, "propose")

    # propose should be passed since explore.artifact.json is present.
    propose_phase = state.phase("propose")  # type: ignore[arg-type]
    assert propose_phase.status == "passed"


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
