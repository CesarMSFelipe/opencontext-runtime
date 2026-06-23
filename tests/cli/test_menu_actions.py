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


def test_config_menu_non_tty_does_not_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    # The config menu loop exits only on "back"; without a TTY the selector would
    # return its default forever. The guard must short-circuit instead of looping.
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    selected: dict[str, bool] = {"called": False}
    monkeypatch.setattr(
        menu_cmd.prompts, "select", lambda *a, **k: selected.__setitem__("called", True)
    )

    menu_cmd.run_config_menu()

    assert selected["called"] is False  # selector never reached


def test_config_menu_lists_unified_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every setting must live in the one config menu — including the unreachable-
    # before entries (memory backend, language) folded in during unification.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(menu_cmd, "_action_header", lambda *a, **k: None)

    captured: dict[str, list] = {}

    def fake_select(message: str, choices: list, **kw: object) -> str:
        captured["keys"] = [c[0] for c in choices if isinstance(c, tuple)]
        return "back"

    monkeypatch.setattr(menu_cmd.prompts, "select", fake_select)
    menu_cmd.run_config_menu()

    for key in ("security", "features", "models", "agents", "plugins", "memory", "language", "sdd"):
        assert key in captured["keys"], f"{key} missing from the unified config menu"


def test_run_memory_backend_writes_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    import opencontext_core.config_sync as cs

    monkeypatch.setattr(menu_cmd, "_action_header", lambda *a, **k: None)
    monkeypatch.setattr(menu_cmd.prompts, "select", lambda *a, **k: "engram")
    written: dict[str, object] = {}

    def fake_set(path: str, value: object, **kw: object) -> bool:
        written["path"] = path
        written["value"] = value
        return True

    monkeypatch.setattr(cs, "set_yaml_key", fake_set)
    menu_cmd._run_memory_backend()

    assert written == {"path": "memory.provider", "value": "engram"}


def test_run_language_writes_ui_language(monkeypatch: pytest.MonkeyPatch) -> None:
    import opencontext_core.config_sync as cs

    monkeypatch.setattr(menu_cmd, "_action_header", lambda *a, **k: None)
    monkeypatch.setattr(menu_cmd.prompts, "select", lambda *a, **k: "es")
    written: dict[str, object] = {}

    def fake_set(path: str, value: object, **kw: object) -> bool:
        written["path"] = path
        written["value"] = value
        return True

    monkeypatch.setattr(cs, "set_yaml_key", fake_set)
    menu_cmd._run_language()

    assert written == {"path": "ui_language", "value": "es"}
