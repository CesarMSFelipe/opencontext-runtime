"""Branded gate panels for oc-new request_approval / blocked next-actions.

Failing tests (TDD):
- When the conductor pauses (kind=request_approval) the human output is a
  branded panel: which phase gated, progress summary, what happens next, and
  the exact commands to continue/inspect — not a raw field dump.
- Blocked runs surface the block reason and a resume command.
- The --json shape is untouched (pure state dump, parseable).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from opencontext_cli.commands.oc_new_cmd import handle_oc_new


def _start_args(tmp_path: Path, *, flow: str | None = None, json_out: bool = False) -> Any:
    return SimpleNamespace(
        root=str(tmp_path),
        json_out=json_out,
        oc_new_command="start",
        task="stepwise gated task",
        flow=flow,
        yes=True,  # skip the preflight; these tests target the gate rendering
        non_interactive=False,
    )


def test_request_approval_renders_branded_panel(tmp_path: Path, capsys: Any) -> None:
    """stepwise start pauses immediately -> gate panel with continue commands."""
    handle_oc_new(_start_args(tmp_path, flow="stepwise"))

    out = capsys.readouterr().out
    # Kind + phase remain visible (agents parse them).
    assert "request_approval" in out
    assert "explore" in out
    # Human guidance: what happens next and the exact commands.
    assert "opencontext oc-new done explore" in out
    assert "opencontext oc-new status" in out
    # The run id is named so the commands are copy-pasteable.
    assert "--run-id" in out


def test_blocked_renders_reason_and_resume_command(tmp_path: Path, capsys: Any) -> None:
    """A blocked state names the reason and the resume command."""
    from opencontext_core.oc_new.conductor import OcNewConductor
    from opencontext_core.oc_new.store import OcNewStore

    conductor = OcNewConductor(tmp_path)
    state = conductor.start("blocked gate task")
    run_id = state.identity.run_id

    # Force a blocked next-action state, then render via the status command.
    from opencontext_core.oc_new.models import NextAction

    blocked = state.model_copy(
        update={
            "blocked_reason": "missing artifacts: explore.artifact.json",
            "next_action": NextAction(
                kind="blocked",
                phase="explore",
                instruction="Cannot run explore; missing: explore.artifact.json",
            ),
        }
    )
    OcNewStore(tmp_path).save(blocked)

    status_args = SimpleNamespace(
        root=str(tmp_path),
        json_out=False,
        oc_new_command="status",
        run_id=run_id,
        watch=False,
    )
    capsys.readouterr()  # clear start output
    handle_oc_new(status_args)

    out = capsys.readouterr().out
    assert "blocked" in out
    assert "missing artifacts: explore.artifact.json" in out
    assert f"opencontext oc-new resume {run_id}" in out


def test_json_shape_untouched_for_request_approval(tmp_path: Path, capsys: Any) -> None:
    """--json emits the pure state dump — no panel chrome on stdout."""
    handle_oc_new(_start_args(tmp_path, flow="stepwise", json_out=True))

    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["next_action"]["kind"] == "request_approval"
    assert data["schema_version"] == "opencontext.oc_new_state.v1"
