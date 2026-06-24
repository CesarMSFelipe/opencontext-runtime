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


def test_config_menu_prefers_the_tui(monkeypatch: pytest.MonkeyPatch) -> None:
    # The config menu is the Textual TUI and nothing else — when it runs,
    # run_config_menu returns without falling back to any selector.
    monkeypatch.setattr("opencontext_cli.tui.run_config_tui", lambda **k: True)
    reached = {"selector": False}
    monkeypatch.setattr(
        menu_cmd.prompts, "select", lambda *a, **k: reached.__setitem__("selector", True) or "back"
    )
    menu_cmd.run_config_menu()
    assert reached["selector"] is False


def test_config_menu_no_tty_points_to_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    # No terminal → no second parallel menu; just a message pointing at the CLI.
    monkeypatch.setattr("opencontext_cli.tui.run_config_tui", lambda **k: False)
    called = {"select": False}
    monkeypatch.setattr(
        menu_cmd.prompts, "select", lambda *a, **k: called.__setitem__("select", True)
    )
    printed: list[str] = []
    monkeypatch.setattr(menu_cmd.console, "print", lambda *a, **k: printed.append(str(a)))
    menu_cmd.run_config_menu()
    assert called["select"] is False
    assert any("needs a terminal" in p for p in printed)


def test_offer_engram_install_skips_when_already_present(monkeypatch: pytest.MonkeyPatch) -> None:
    import opencontext_core.memory.engram_bridge as eb

    monkeypatch.setattr(eb, "detect_engram", lambda: True)
    asked = {"confirm": False}
    monkeypatch.setattr(
        menu_cmd.prompts, "confirm", lambda *a, **k: asked.__setitem__("confirm", True) or True
    )
    menu_cmd._offer_engram_install()
    assert asked["confirm"] is False  # never prompts when Engram is already there


def test_offer_engram_install_declined_installs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    import opencontext_core.memory.engram_bridge as eb

    monkeypatch.setattr(eb, "detect_engram", lambda: False)
    monkeypatch.setattr(menu_cmd.prompts, "confirm", lambda *a, **k: False)
    ran = {"called": False}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: ran.__setitem__("called", True))
    menu_cmd._offer_engram_install()
    assert ran["called"] is False


def test_offer_engram_install_runs_installer_on_accept(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    import subprocess

    import opencontext_core.memory.engram_bridge as eb

    # Not present, then present after the install runs.
    detect = iter([False, True])
    monkeypatch.setattr(eb, "detect_engram", lambda: next(detect))
    monkeypatch.setattr(menu_cmd.prompts, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(shutil, "which", lambda name: None)  # no pipx → pip path

    captured: dict[str, list] = {}

    class _Result:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **k: captured.__setitem__("cmd", cmd) or _Result()
    )
    menu_cmd._offer_engram_install()
    assert "engram" in captured["cmd"]  # an install of the engram package was issued
