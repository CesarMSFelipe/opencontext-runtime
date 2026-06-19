"""Regression tests for the interactive menu action dispatchers.

These paths are only reachable with a real terminal, so the suite never used to
touch them — which is how two crashes shipped: ``_run_backups`` called
``Prompt.ask`` and ``_run_uninstall`` called ``Confirm.ask`` without importing
either symbol (NameError on entry). They now go through the navigable
``prompts`` helpers; these tests drive the dispatch logic with the selector
stubbed so a regression fails fast in CI instead of in a user's terminal.
"""

from __future__ import annotations

import pytest

from opencontext_cli.commands import menu_cmd
from opencontext_core import wizard


def test_run_backups_back_exits_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    # Previously raised NameError: name 'Prompt' is not defined.
    monkeypatch.setattr(menu_cmd.prompts, "select", lambda *a, **k: "back")
    menu_cmd._run_backups()


def test_run_backups_dispatches_then_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    choices = iter(["list", "back"])
    monkeypatch.setattr(menu_cmd.prompts, "select", lambda *a, **k: next(choices))
    monkeypatch.setattr(menu_cmd.prompts, "pause", lambda *a, **k: None)
    called: dict[str, bool] = {}
    monkeypatch.setattr(menu_cmd, "_list_backups", lambda: called.__setitem__("list", True))

    menu_cmd._run_backups()

    assert called.get("list") is True


def test_run_uninstall_decline_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    # Previously raised NameError: name 'Confirm' is not defined.
    import opencontext_cli.main as cli_main

    proceeded: dict[str, bool] = {"clean": False}
    monkeypatch.setattr(menu_cmd.prompts, "confirm", lambda *a, **k: False)
    monkeypatch.setattr(cli_main, "_clean", lambda *a, **k: proceeded.__setitem__("clean", True))

    menu_cmd._run_uninstall()

    assert proceeded["clean"] is False


def test_wizard_menu_non_tty_does_not_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    # The menu loop exits only on "quit"; without a TTY the selector would return
    # its default forever. The guard must short-circuit instead of looping.
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    selected: dict[str, bool] = {"called": False}
    monkeypatch.setattr(
        wizard.prompts, "select", lambda *a, **k: selected.__setitem__("called", True)
    )

    wizard.run_wizard_menu()

    assert selected["called"] is False  # selector never reached
