"""PROD-004 / B1: `run` prints an actionable stderr hint on needs_executor/needs_provider.

The hint must name at least one concrete remedy and go to STDERR so that the
``--json`` STDOUT payload stays pure JSON.

C15 update: RuntimeApi._legacy_status now preserves OC Flow terminal vocabulary
(needs_executor, needs_provider, …) so result.status already carries the correct
value.  The stub _FakeResult.status is set to the legacy_status directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from opencontext_cli.commands.run_cmd import handle_run_exec


def _args(tmp_path: Path, *, json_out: bool) -> SimpleNamespace:
    return SimpleNamespace(
        task="Fix failing test",
        workflow="auto",
        lane="fast",
        profile="balanced",
        resume=None,
        root=str(tmp_path),
        config=None,
        json=json_out,
    )


def _make_stub_api(legacy_status: str):
    """Return a fake RuntimeApi class whose run() carries the given status.

    _legacy_status now preserves OC Flow terminal vocabulary unchanged, so
    result.status == legacy_status for needs_executor / needs_provider.
    """

    class _FakeLegacy:
        status = legacy_status
        workflow_selection: dict[str, str] = {}

    class _FakeResult:
        run_id = "r1"
        # _legacy_status passes OC Flow terminal vocab through unchanged;
        # set status to match so callers using result.status see the right value.
        status = legacy_status
        legacy = _FakeLegacy()

    class _FakeSession:
        session_id = "sess-test"
        status = "created"
        session_path = "/tmp/s"

    class _FakeApi:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def start_session(self, request: Any) -> Any:
            return _FakeSession()

        def run(self, request: Any) -> Any:
            return _FakeResult()

    return _FakeApi


def test_needs_executor_prints_hint_to_stderr(tmp_path: Path, capsys: Any) -> None:
    with patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api("needs_executor")):
        handle_run_exec(_args(tmp_path, json_out=True))

    captured = capsys.readouterr()
    # STDOUT is pure JSON (no hint leaked into the machine payload).
    payload = json.loads(captured.out)
    assert payload["status"] == "needs_executor"
    # The hint is on STDERR and names at least one concrete remedy.
    assert "Hint:" in captured.err
    assert "ANTHROPIC_API_KEY" in captured.err
    assert "test_stub" in captured.err
    assert "doctor" in captured.err


def test_needs_provider_prints_hint(tmp_path: Path, capsys: Any) -> None:
    with patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api("needs_provider")):
        handle_run_exec(_args(tmp_path, json_out=False))

    captured = capsys.readouterr()
    assert "Hint:" in captured.err
    assert "MCP sampler" in captured.err


def test_completed_run_emits_no_hint(tmp_path: Path, capsys: Any) -> None:
    with patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api("completed")):
        handle_run_exec(_args(tmp_path, json_out=True))

    captured = capsys.readouterr()
    assert "Hint:" not in captured.err
