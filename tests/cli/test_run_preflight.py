"""Guided preflight for `opencontext run` — interactive briefing before execution.

Failing tests (TDD):
- On an interactive TTY (no --json/--yes), a branded preflight panel renders the
  selected workflow + reason, node sequence, artifacts, gates, the cost estimate
  (surfaced, not stderr-only), and memory/KG/compression status — then asks.
- --json, --yes, --non-interactive, and non-TTY sessions skip the preflight
  entirely (no prompt is ever invoked; scripts see today's behavior).
- Choosing "Change workflow" / "Change lane" applies the choice to the run.
- Choosing "Cancel" exits without starting a session or running anything.
- --json stdout stays pure JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from opencontext_cli.commands.run_cmd import handle_run_exec


def _args(
    tmp_path: Path,
    *,
    json_out: bool = False,
    yes: bool = False,
    non_interactive: bool = False,
    workflow: str = "oc-flow",
    lane: str = "fast",
) -> SimpleNamespace:
    return SimpleNamespace(
        task="Fix failing test",
        workflow=workflow,
        lane=lane,
        profile="balanced",
        resume=None,
        root=str(tmp_path),
        config=None,
        json=json_out,
        yes=yes,
        non_interactive=non_interactive,
    )


class _Recorder:
    """Records RuntimeApi calls made by handle_run_exec."""

    def __init__(self) -> None:
        self.start_session_calls: list[Any] = []
        self.run_calls: list[Any] = []


def _make_stub_api(recorder: _Recorder) -> type:
    class _FakeLegacy:
        status = "completed"
        workflow_selection: dict[str, str] = {}  # noqa: RUF012

    class _FakeResult:
        run_id = "r-preflight-test"
        status = "completed"
        legacy = _FakeLegacy()

    class _FakeSession:
        session_id = "sess-preflight-test"
        status = "created"
        session_path = "/tmp/s"

    class _FakeApi:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        def start_session(self, request: Any) -> Any:
            recorder.start_session_calls.append(request)
            return _FakeSession()

        def run(self, request: Any) -> Any:
            recorder.run_calls.append(request)
            return _FakeResult()

    return _FakeApi


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "opencontext.yaml").write_text("{}", encoding="utf-8")


def test_preflight_shown_on_tty_then_proceed(tmp_path: Path, capsys: Any) -> None:
    """On a TTY the preflight briefing renders and Proceed executes the run."""
    _write_config(tmp_path)
    recorder = _Recorder()

    with (
        patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api(recorder)),
        patch("opencontext_cli.flow_preflight._is_tty", return_value=True),
        patch("opencontext_core.prompts.select", return_value="proceed") as sel,
    ):
        handle_run_exec(_args(tmp_path))

    out = capsys.readouterr().out
    assert sel.called, "Preflight prompt must be shown on a TTY"
    assert len(recorder.run_calls) == 1, "Proceed must execute the run"
    # Briefing content: workflow + reason, sequence, artifacts, gates, estimate,
    # and subsystem status must all be visible on stdout.
    assert "oc-flow" in out
    assert "gather_context" in out or "Gather Context" in out
    assert "patch.diff" in out
    assert "inspection" in out.lower()
    assert "estimate" in out.lower()
    assert "memory" in out.lower()
    assert "compression" in out.lower()
    # Detail-card format (config-TUI style) for the options.
    assert "Current:" in out
    assert "Effect:" in out
    assert "Recommended:" in out
    assert "Risk / note:" in out
    assert "CLI:" in out


def test_preflight_skipped_for_json(tmp_path: Path, capsys: Any) -> None:
    """--json implies non-interactive: no prompt, stdout stays pure JSON."""
    _write_config(tmp_path)
    recorder = _Recorder()

    with (
        patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api(recorder)),
        patch("opencontext_cli.flow_preflight._is_tty", return_value=True),
        patch("opencontext_core.prompts.select") as sel,
    ):
        handle_run_exec(_args(tmp_path, json_out=True))

    out = capsys.readouterr().out
    assert not sel.called, "--json must skip the preflight prompt"
    payload = json.loads(out)
    # Canonical status surfaces in `status`; the raw vocabulary stays additive.
    assert payload["status"] == "passed"
    assert payload["legacy_status"] == "completed"
    assert len(recorder.run_calls) == 1


def test_preflight_skipped_for_yes_flag(tmp_path: Path, capsys: Any) -> None:
    """--yes skips the preflight and runs directly."""
    _write_config(tmp_path)
    recorder = _Recorder()

    with (
        patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api(recorder)),
        patch("opencontext_cli.flow_preflight._is_tty", return_value=True),
        patch("opencontext_core.prompts.select") as sel,
    ):
        handle_run_exec(_args(tmp_path, yes=True))

    assert not sel.called
    assert len(recorder.run_calls) == 1


def test_preflight_skipped_for_non_interactive_flag(tmp_path: Path, capsys: Any) -> None:
    """--non-interactive skips the preflight and runs directly."""
    _write_config(tmp_path)
    recorder = _Recorder()

    with (
        patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api(recorder)),
        patch("opencontext_cli.flow_preflight._is_tty", return_value=True),
        patch("opencontext_core.prompts.select") as sel,
    ):
        handle_run_exec(_args(tmp_path, non_interactive=True))

    assert not sel.called
    assert len(recorder.run_calls) == 1


def test_preflight_skipped_without_tty(tmp_path: Path, capsys: Any) -> None:
    """Non-TTY (scripts, CI) behaves exactly like today: no prompt, direct run."""
    _write_config(tmp_path)
    recorder = _Recorder()

    with (
        patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api(recorder)),
        patch("opencontext_cli.flow_preflight._is_tty", return_value=False),
        patch("opencontext_core.prompts.select") as sel,
    ):
        handle_run_exec(_args(tmp_path))

    assert not sel.called
    assert len(recorder.run_calls) == 1


def test_preflight_change_workflow_applies(tmp_path: Path, capsys: Any) -> None:
    """Change workflow -> auto is threaded into the actual RunRequest."""
    _write_config(tmp_path)
    recorder = _Recorder()

    def fake_select(message: str, choices: Any, **kw: Any) -> str:
        values = [c[0] if isinstance(c, tuple) else c for c in choices]
        if "auto" in values:  # the workflow sub-selector
            return "auto"
        # Main menu: first change the workflow, then proceed.
        if not fake_select.workflow_changed:  # type: ignore[attr-defined]
            fake_select.workflow_changed = True  # type: ignore[attr-defined]
            return "workflow"
        return "proceed"

    fake_select.workflow_changed = False  # type: ignore[attr-defined]

    with (
        patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api(recorder)),
        patch("opencontext_cli.flow_preflight._is_tty", return_value=True),
        patch("opencontext_core.prompts.select", side_effect=fake_select),
    ):
        handle_run_exec(_args(tmp_path))

    assert len(recorder.run_calls) == 1
    assert recorder.run_calls[0].workflow_id == "auto"


def test_preflight_change_lane_applies(tmp_path: Path, capsys: Any) -> None:
    """Change lane -> careful is reflected in the surfaced cost estimate."""
    _write_config(tmp_path)
    recorder = _Recorder()

    def fake_select(message: str, choices: Any, **kw: Any) -> str:
        values = [c[0] if isinstance(c, tuple) else c for c in choices]
        if "careful" in values:  # the lane sub-selector
            return "careful"
        if not fake_select.lane_changed:  # type: ignore[attr-defined]
            fake_select.lane_changed = True  # type: ignore[attr-defined]
            return "lane"
        return "proceed"

    fake_select.lane_changed = False  # type: ignore[attr-defined]

    with (
        patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api(recorder)),
        patch("opencontext_cli.flow_preflight._is_tty", return_value=True),
        patch("opencontext_core.prompts.select", side_effect=fake_select),
    ):
        handle_run_exec(_args(tmp_path))

    captured = capsys.readouterr()
    assert len(recorder.run_calls) == 1
    # The estimate hint reflects the final lane choice.
    assert "careful" in captured.err + captured.out


def test_preflight_cancel_runs_nothing(tmp_path: Path, capsys: Any) -> None:
    """Cancel exits cleanly without starting a session or running the workflow."""
    _write_config(tmp_path)
    recorder = _Recorder()

    with (
        patch("opencontext_core.runtime.api.RuntimeApi", _make_stub_api(recorder)),
        patch("opencontext_cli.flow_preflight._is_tty", return_value=True),
        patch("opencontext_core.prompts.select", return_value="cancel"),
    ):
        handle_run_exec(_args(tmp_path))

    assert recorder.start_session_calls == []
    assert recorder.run_calls == []
    out = capsys.readouterr().out
    assert "cancel" in out.lower()
