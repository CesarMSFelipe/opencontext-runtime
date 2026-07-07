"""Tests for the oc-new CLI command."""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

from opencontext_cli.main import main


def _run(argv: list[str], monkeypatch, tmp_path) -> int:
    monkeypatch.chdir(tmp_path)
    with patch.object(sys, "argv", ["opencontext", *argv]):
        try:
            main()
            return 0
        except SystemExit as e:
            return int(e.code or 0)


def test_oc_new_start(tmp_path, monkeypatch, capsys):
    rc = _run(["oc-new", "start", "Add graph health command"], monkeypatch, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "explore" in out
    assert "spawn_subagent" in out


def test_oc_new_start_json(tmp_path, monkeypatch, capsys):
    rc = _run(["oc-new", "--json", "start", "test task"], monkeypatch, tmp_path)
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["current_phase"] == "explore"
    assert data["schema_version"] == "opencontext.oc_new_state.v1"


def test_oc_new_status_after_start(tmp_path, monkeypatch, capsys):
    _run(["oc-new", "start", "My task"], monkeypatch, tmp_path)
    capsys.readouterr()  # clear start output

    rc = _run(["oc-new", "status"], monkeypatch, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "My task" in out
    assert "explore" in out


def test_oc_new_next(tmp_path, monkeypatch, capsys):
    _run(["oc-new", "start", "My task"], monkeypatch, tmp_path)
    capsys.readouterr()

    rc = _run(["oc-new", "next"], monkeypatch, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "spawn_subagent" in out


def test_oc_new_list_empty(tmp_path, monkeypatch, capsys):
    rc = _run(["oc-new", "list"], monkeypatch, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "No oc-new runs" in out


def test_oc_new_list(tmp_path, monkeypatch, capsys):
    _run(["oc-new", "start", "Task A"], monkeypatch, tmp_path)
    capsys.readouterr()

    rc = _run(["oc-new", "list"], monkeypatch, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Task A" in out


def test_oc_new_done_advances_phase(tmp_path, monkeypatch, capsys):
    from opencontext_core.oc_new.store import OcNewStore
    from opencontext_core.workflow.phase_result import PhaseResultEnvelope

    _run(["oc-new", "start", "test task"], monkeypatch, tmp_path)
    capsys.readouterr()

    store = OcNewStore(tmp_path)
    state = store.latest()
    assert state is not None
    run_id = state.identity.run_id

    # Create the artifact that propose needs (explore.artifact.json)
    run_dir = tmp_path / ".opencontext" / "runs" / run_id
    (run_dir / "explore.artifact.json").write_text("{}", encoding="utf-8")

    # Write the phase-result envelope (required by conductor.mark_done).
    envelope = PhaseResultEnvelope(
        run_id=run_id,
        change_id=state.identity.change_id,
        phase="explore",
        status="passed",
        duration_s=0.0,
        artifacts=["explore.artifact.json"],
    )
    (run_dir / "phase-result.explore.json").write_text(envelope.model_dump_json(), encoding="utf-8")

    rc = _run(
        ["oc-new", "done", "explore", "--run-id", run_id, "--artifact", "explore.artifact.json"],
        monkeypatch,
        tmp_path,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "propose" in out


def test_oc_new_resume(tmp_path, monkeypatch, capsys):
    from opencontext_core.oc_new.store import OcNewStore

    _run(["oc-new", "start", "My task"], monkeypatch, tmp_path)
    capsys.readouterr()

    store = OcNewStore(tmp_path)
    run_id = store.latest().identity.run_id

    rc = _run(["oc-new", "resume", run_id], monkeypatch, tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "explore" in out


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
