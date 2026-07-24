"""Bare ``opencontext`` in a fresh project must onboard, not open the config menu.

A first-time developer who runs a bare ``opencontext`` should be pointed at the
complete install flow and told how to start a task — never dropped into the
config TUI (or, non-tty, a terse "interactive menu needs a terminal" error).

These tests exercise the ``command is None`` branch of ``_dispatch`` for a fresh
project (``is_first_run`` True, dir looks like a project):

* non-tty  → prints the first-run guidance and does NOT open the menu
* tty + YES → runs the SAME complete flow as ``opencontext install --yes``
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from opencontext_cli import main as cli_main


class _RecordingConsole:
    """Minimal console stand-in that records every printed/paneled string."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, *args: Any, **_kwargs: Any) -> None:
        self.lines.append(" ".join(str(a) for a in args))

    def panel(self, content: str, *_args: Any, **_kwargs: Any) -> None:
        self.lines.append(str(content))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _bare_args() -> Any:
    return cli_main._build_parser().parse_args([])


def test_bare_command_non_tty_prints_first_run_guidance_and_skips_menu() -> None:
    """Non-tty fresh project: guidance is printed, the config menu is NOT invoked."""
    rec = _RecordingConsole()
    menu_called = {"yes": False}
    install_called = {"yes": False}

    def _fake_menu() -> None:
        menu_called["yes"] = True

    def _fake_install(_args: Any) -> None:
        install_called["yes"] = True

    with (
        patch.object(cli_main, "is_first_run", return_value=True),
        patch.object(cli_main, "_looks_like_project", return_value=True),
        patch.object(cli_main, "console", rec),
        patch.object(cli_main, "_install", _fake_install),
        patch("sys.stdout.isatty", return_value=False),
        # Guard: if the branch ever fell through to the menu, this would flip it.
        patch(
            "opencontext_cli.commands.menu_cmd.run_main_menu",
            _fake_menu,
        ),
    ):
        cli_main._dispatch(_bare_args())

    out = rec.text
    # The two things the user was missing: the install command and the task entry point.
    assert "opencontext install --yes" in out
    assert "/oc-new" in out
    assert "oc-new start" in out  # explicit terminal spelling
    # Must NOT drop the developer into the config menu, and must not run install unprompted.
    assert menu_called["yes"] is False
    assert install_called["yes"] is False
    # Must NOT emit the terse "needs a terminal" message the user complained about.
    assert "needs a terminal" not in out


def test_bare_command_tty_yes_runs_install_flow() -> None:
    """TTY fresh project + YES confirm: the complete install flow runs (install --yes)."""
    rec = _RecordingConsole()
    captured: dict[str, Any] = {}

    def _fake_install(args: Any) -> None:
        captured["args"] = args

    def _fake_confirm(_message: str, *, default: bool = True) -> bool:
        captured["confirm_default"] = default
        return True

    with (
        patch.object(cli_main, "is_first_run", return_value=True),
        patch.object(cli_main, "_looks_like_project", return_value=True),
        patch.object(cli_main, "console", rec),
        patch.object(cli_main, "_install", _fake_install),
        patch("sys.stdout.isatty", return_value=True),
        patch("opencontext_core.prompts.confirm", _fake_confirm),
    ):
        cli_main._dispatch(_bare_args())

    # The install pipeline was invoked with the install command + --yes defaults.
    assert "args" in captured, "install flow was not invoked on YES"
    install_args = captured["args"]
    assert getattr(install_args, "command", None) == "install"
    assert getattr(install_args, "yes", False) is True
    # The confirm defaulted to YES (single, low-friction prompt).
    assert captured.get("confirm_default") is True


def test_bare_command_tty_no_falls_back_to_menu() -> None:
    """TTY fresh project + NO confirm: does not install, offers the menu instead."""
    rec = _RecordingConsole()
    menu_called = {"yes": False}
    install_called = {"yes": False}

    with (
        patch.object(cli_main, "is_first_run", return_value=True),
        patch.object(cli_main, "_looks_like_project", return_value=True),
        patch.object(cli_main, "console", rec),
        patch.object(cli_main, "_install", lambda _a: install_called.__setitem__("yes", True)),
        patch("sys.stdout.isatty", return_value=True),
        patch("opencontext_core.prompts.confirm", lambda *_a, **_k: False),
        patch(
            "opencontext_cli.commands.menu_cmd.run_main_menu",
            lambda: menu_called.__setitem__("yes", True),
        ),
    ):
        cli_main._dispatch(_bare_args())

    assert install_called["yes"] is False
    assert menu_called["yes"] is True
    assert "opencontext install" in rec.text


def test_bare_command_not_first_run_opens_menu_not_onboarding() -> None:
    """Established project: bare command still opens the menu (no regression)."""
    menu_called = {"yes": False}

    with (
        patch.object(cli_main, "is_first_run", return_value=False),
        patch(
            "opencontext_cli.commands.menu_cmd.run_main_menu",
            lambda: menu_called.__setitem__("yes", True),
        ),
    ):
        cli_main._dispatch(_bare_args())

    assert menu_called["yes"] is True
