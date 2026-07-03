"""Guided preflight for `opencontext oc-new start` — flow briefing before start.

Failing tests (TDD):
- On an interactive TTY, starting a run first renders a branded briefing: the
  resolved flow_mode + what it means, the phase list, artifact store mode, TDD
  mode, and delivery strategy — then asks for the execution mode and confirms.
- The chosen flow mode applies to THIS RUN ONLY (opencontext.yaml untouched) and
  a persistence hint (`opencontext config set sdd.flow_mode <mode>`) is printed.
- --json, --yes, --non-interactive, and non-TTY skip the preflight entirely.
- Declining the confirmation starts nothing.
- --json output shape is unchanged (pure JSON state dump).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from opencontext_cli.commands.oc_new_cmd import handle_oc_new


def _args(
    tmp_path: Path,
    *,
    task: str = "add health check",
    flow: str | None = None,
    json_out: bool = False,
    yes: bool = False,
    non_interactive: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        root=str(tmp_path),
        json_out=json_out,
        oc_new_command="start",
        task=task,
        flow=flow,
        yes=yes,
        non_interactive=non_interactive,
    )


def _tty(value: bool) -> Any:
    return patch("opencontext_cli.flow_preflight._is_tty", return_value=value)


def test_preflight_shown_on_tty_and_confirm_starts(tmp_path: Path, capsys: Any) -> None:
    """TTY start renders the flow briefing, asks, and starts on confirmation."""
    with (
        _tty(True),
        patch("opencontext_core.prompts.select", return_value="automatic") as sel,
        patch("opencontext_core.prompts.confirm", return_value=True) as conf,
    ):
        handle_oc_new(_args(tmp_path))

    out = capsys.readouterr().out
    assert sel.called and conf.called
    # Briefing content: mode meanings, phases, store/TDD/delivery knobs.
    assert "automatic" in out
    assert "stepwise" in out
    assert "hybrid" in out
    assert "explore" in out and "apply" in out and "archive" in out
    assert "artifact store" in out.lower()
    assert "tdd" in out.lower()
    assert "delivery" in out.lower()
    # Detail-card format per option (config-TUI style).
    assert "Current:" in out
    assert "Effect:" in out
    assert "Recommended:" in out
    assert "Risk / note:" in out
    assert "CLI:" in out
    # The run actually started.
    assert "spawn_subagent" in out


def test_preflight_mode_choice_applies_this_run_only(tmp_path: Path, capsys: Any) -> None:
    """Choosing stepwise applies to this run; opencontext.yaml is not written."""
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text("sdd:\n  flow_mode: automatic\n", encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", return_value="stepwise"),
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path))

    out = capsys.readouterr().out
    # stepwise pauses before the first phase -> request_approval.
    assert "request_approval" in out
    # Persistence hint printed; config untouched.
    assert "opencontext config set sdd.flow_mode stepwise" in out
    assert config_path.read_text(encoding="utf-8") == before


def test_preflight_skipped_for_json(tmp_path: Path, capsys: Any) -> None:
    """--json skips the preflight; stdout is pure JSON with the same shape."""
    with (
        _tty(True),
        patch("opencontext_core.prompts.select") as sel,
        patch("opencontext_core.prompts.confirm") as conf,
    ):
        handle_oc_new(_args(tmp_path, json_out=True))

    out = capsys.readouterr().out
    assert not sel.called and not conf.called
    data = json.loads(out)
    assert data["schema_version"] == "opencontext.oc_new_state.v1"
    assert data["current_phase"] == "explore"


def test_preflight_skipped_for_yes_and_non_interactive(tmp_path: Path, capsys: Any) -> None:
    """--yes / --non-interactive start directly without prompting."""
    with (
        _tty(True),
        patch("opencontext_core.prompts.select") as sel,
        patch("opencontext_core.prompts.confirm") as conf,
    ):
        handle_oc_new(_args(tmp_path, yes=True))
        handle_oc_new(_args(tmp_path, task="second task", non_interactive=True))

    out = capsys.readouterr().out
    assert not sel.called and not conf.called
    assert "spawn_subagent" in out


def test_preflight_skipped_without_tty(tmp_path: Path, capsys: Any) -> None:
    """Non-TTY behaves exactly like today: no prompt, run starts."""
    with (
        _tty(False),
        patch("opencontext_core.prompts.select") as sel,
    ):
        handle_oc_new(_args(tmp_path))

    out = capsys.readouterr().out
    assert not sel.called
    assert "spawn_subagent" in out


def test_preflight_decline_starts_nothing(tmp_path: Path, capsys: Any) -> None:
    """Declining the confirmation leaves no run behind."""
    from opencontext_core.oc_new.store import OcNewStore

    with (
        _tty(True),
        patch("opencontext_core.prompts.select", return_value="automatic"),
        patch("opencontext_core.prompts.confirm", return_value=False),
    ):
        handle_oc_new(_args(tmp_path))

    out = capsys.readouterr().out
    assert "cancel" in out.lower()
    assert OcNewStore(tmp_path).list_runs() == []


def test_explicit_flow_flag_is_preflight_default(tmp_path: Path, capsys: Any) -> None:
    """--flow hybrid seeds the preflight; keeping it runs hybrid semantics."""
    with (
        _tty(True),
        patch("opencontext_core.prompts.select", return_value="hybrid") as sel,
        patch("opencontext_core.prompts.confirm", return_value=True),
    ):
        handle_oc_new(_args(tmp_path, flow="hybrid"))

    assert sel.called
    assert sel.call_args.kwargs.get("default") == "hybrid"
