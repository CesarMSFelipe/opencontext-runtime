"""UX façade tests — ``opencontext workflow {start,status,approve,receipt}``.

Each verb must reach the existing ``OcNewConductor`` / ``OcNewStore`` /
``AgenticReceipt`` machinery within ONE delegation hop. Tests assert the call
path by patching the conductor class at the *ux_cmd* module's import site.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from opencontext_cli.main import main
from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import ChangeIdentity, NextAction, OcNewRunState, PhaseState


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> int:
    monkeypatch.chdir(tmp_path)
    with patch.object(sys, "argv", ["opencontext", *argv]):
        try:
            main()
            return 0
        except SystemExit as exc:
            return int(exc.code or 0)


def _seed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run ``workflow start`` to create a real state.json; return run_id."""
    assert _run(["workflow", "start", "test task"], monkeypatch, tmp_path) == 0
    return sorted((tmp_path / ".opencontext" / "runs").iterdir())[-1].name


def _fake_state(task: str = "fake") -> OcNewRunState:
    identity = ChangeIdentity.from_task(task)
    phases = [PhaseState(name=p.name) for p in OC_NEW_FLOW]
    return OcNewRunState(
        identity=identity,
        task=task,
        phases=phases,
        current_phase="explore",
        next_action=NextAction(kind="spawn_subagent", phase="explore", instruction="run"),
    )


@pytest.mark.parametrize("verb", ["start", "status", "approve", "receipt"])
def test_workflow_verb_registered(verb: str) -> None:
    from opencontext_cli.main import _build_parser

    parser = _build_parser()
    for action in parser._actions:  # type: ignore[attr-defined]
        choices = getattr(action, "choices", None)
        if choices and "workflow" in choices:
            wf = choices["workflow"]
            for sub in wf._actions:  # type: ignore[attr-defined]
                sub_choices = getattr(sub, "choices", None)
                if sub_choices and verb in sub_choices:
                    assert sub_choices[verb] is not None
                    return
    raise AssertionError(f"verb {verb!r} not registered under workflow subparser")


def test_workflow_start_delegates_to_oc_new_conductor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """start verb reaches OcNewConductor.start within one hop."""
    with patch(
        "opencontext_cli.commands.ux_cmd.OcNewConductor.start",
        autospec=True,
        return_value=_fake_state(),
    ) as mock_start:
        assert _run(["workflow", "start", "x"], monkeypatch, tmp_path) == 0
    assert mock_start.called


def test_workflow_status_delegates_to_oc_new_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """status verb reaches OcNewStore.load within one hop."""
    _seed_run(tmp_path, monkeypatch)
    with patch(
        "opencontext_cli.commands.ux_cmd.OcNewStore.load",
        autospec=True,
        return_value=_fake_state(),
    ) as mock_load:
        assert _run(["workflow", "status"], monkeypatch, tmp_path) == 0
    assert mock_load.called


def test_workflow_approve_writes_approval_and_delegates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """approve writes run-dir approval.json then delegates resume to conductor."""
    run_id = _seed_run(tmp_path, monkeypatch)
    with patch(
        "opencontext_cli.commands.ux_cmd.OcNewConductor.resume",
        autospec=True,
        return_value=_fake_state("after-approve"),
    ) as mock_resume:
        assert _run(["workflow", "approve", "--run-id", run_id], monkeypatch, tmp_path) == 0
    approval_path = tmp_path / ".opencontext" / "runs" / run_id / "approval.json"
    assert approval_path.exists()
    payload = json.loads(approval_path.read_text())
    assert payload.get("status") == "approved" or payload.get("approved") is True
    assert mock_resume.called


def test_workflow_status_uses_projection_no_extra_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """status projection must be read-only — no new files in run dir."""
    run_id = _seed_run(tmp_path, monkeypatch)
    before = set((tmp_path / ".opencontext" / "runs" / run_id).iterdir())
    assert _run(["workflow", "status"], monkeypatch, tmp_path) == 0
    after = set((tmp_path / ".opencontext" / "runs" / run_id).iterdir())
    assert before == after


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
