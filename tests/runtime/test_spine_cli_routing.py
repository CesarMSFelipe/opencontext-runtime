"""Commit-007: CLI ``opencontext run`` routes via RuntimeApi (amendment A1).

Per commit-007 in the v2 plan, the CLI's ``handle_run_exec`` branches on
``compat.is_migrated_flag("rt-spine")``. When the flag is on, it routes
through ``start_session()`` + ``run()`` -- NEVER through ``run_workflow``
(amendment A1 forbids that name on RuntimeApi). When the flag is off, it
keeps the existing OC Flow path byte-identical.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from opencontext_cli.commands.run_cmd import handle_run_exec
from opencontext_core.compat.migration import MIGRATION_LEDGER, MigrationState


def _args(tmp_path: Path, **overrides: Any) -> argparse.Namespace:
    base = {
        "task": "fix the failing test",
        "workflow": "oc-flow",
        "lane": "fast",
        "profile": "balanced",
        "resume": None,
        "root": str(tmp_path),
        "config": None,
        "json": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_spine_routes_via_start_session_then_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spine branch calls start_session then run; never run_workflow.

    The runtime facade exposes a 9-method session-first contract (A1); the
    CLI MUST NOT call a non-existent ``run_workflow`` shim. This test pins
    that contract by recording the call shape and asserting no such symbol
    is used.
    """
    from opencontext_core.runtime.api import RunResult, SessionRef

    fake_session = SessionRef(session_id="sess-x", status="created", session_path=str(tmp_path))
    fake_result = RunResult(run_id="run-x", status="completed", legacy=None)

    sequence: list[str] = []

    class FakeApi:
        def __init__(self, *a: Any, **kw: Any) -> None:
            sequence.append("RuntimeApi.__init__")

        def start_session(self, request: Any) -> Any:
            sequence.append(f"start_session({request.task!r})")
            return fake_session

        def run(self, request: Any) -> Any:
            sequence.append(f"run({request.workflow_id!r})")
            return fake_result

    # Reject run_workflow if any code path tries to use it.
    with patch("opencontext_core.compat.is_migrated_flag", return_value=True):
        with patch("opencontext_core.runtime.api.RuntimeApi", FakeApi):
            handle_run_exec(_args(tmp_path))

    # No "run_workflow" call anywhere in the sequence.
    for entry in sequence:
        assert "run_workflow" not in entry, entry

    # Order is init -> start_session -> run.
    assert sequence[0] == "RuntimeApi.__init__"
    assert sequence[1] == "start_session('fix the failing test')"
    assert sequence[2] == "run('oc-flow')"


def test_spine_run_request_carries_session_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The RunRequest sent to api.run() carries the session_id from start_session.

    Pins the A1 session-first contract: the CLI does not invent a run_id;
    it threads the session_id returned by start_session through to run.
    """
    from opencontext_core.runtime.api import RunResult, SessionRef

    fake_session = SessionRef(
        session_id="sess-threaded", status="created", session_path=str(tmp_path)
    )
    fake_result = RunResult(run_id="run-threaded", status="completed", legacy=None)

    captured: dict[str, Any] = {}

    class FakeApi:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def start_session(self, request: Any) -> Any:
            return fake_session

        def run(self, request: Any) -> Any:
            captured["session_id"] = request.session_id
            captured["workflow_id"] = request.workflow_id
            captured["task"] = request.task
            return fake_result

    with patch("opencontext_core.compat.is_migrated_flag", return_value=True):
        with patch("opencontext_core.runtime.api.RuntimeApi", FakeApi):
            handle_run_exec(_args(tmp_path))

    assert captured["session_id"] == "sess-threaded"
    assert captured["workflow_id"] == "oc-flow"
    assert captured["task"] == "fix the failing test"


# ---------- sanity: ledger still has the rt-spine entry -----------------------
def test_rt_spine_ledger_entry_is_migrated() -> None:
    """C15: the rt-spine ledger entry must be in the 'migrated' state after the flip."""
    matches = [m for m in MIGRATION_LEDGER.modules if (m.flag or "").endswith("rt-spine")]
    assert matches, "rt-spine must be in the MIGRATION_LEDGER"
    assert matches[0].state is MigrationState.migrated, (
        f"Expected 'migrated' after C15 flip, got: {matches[0].state}"
    )
