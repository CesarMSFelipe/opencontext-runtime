"""CFG-004 / PROFILES-RUNTIME: interface.* settings gate real CLI/TUI entry points.

The ``ci`` profile resolves ``interface.interactive=false``, ``tui=false`` and
``json_default=true`` — and the entry points must CONSUME those values: the TUI
refuses to launch, the config wizard/menu falls back to non-interactive, and
``config show`` defaults to JSON. The ``local`` profile keeps the interactive
paths enabled.
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from opencontext_cli.commands.config_cmd import handle_config
from opencontext_cli.commands.tui_cmd import handle_tui
from opencontext_cli.contracts.exit_codes import ExitCode


def _workspace(tmp_path: Path, profile: str) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "opencontext.yaml").write_text(
        f"version: 2\nprofile: {profile}\nproject:\n  name: demo\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture()
def hermetic(monkeypatch, tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))  # no real global config / user prefs
    monkeypatch.delenv("OPENCONTEXT_ORG_CONFIG", raising=False)
    monkeypatch.delenv("OPENCONTEXT_PROFILE", raising=False)
    return home


def test_ci_profile_refuses_tui(hermetic, tmp_path: Path, monkeypatch, capsys) -> None:
    """CFG-004: profile ci (interface.tui=false) refuses `opencontext tui` with a readable error."""
    ws = _workspace(tmp_path / "ws", profile="ci")
    monkeypatch.chdir(ws)  # handle_tui chdirs; ensure restoration

    code = handle_tui(Namespace(root=str(ws), smoke=False))

    assert code == int(ExitCode.CONFIG_INVALID)
    err = capsys.readouterr().err
    assert "interface.tui=false" in err
    assert "disabled" in err


def test_local_profile_does_not_refuse_tui_at_the_gate(
    hermetic, tmp_path: Path, monkeypatch, capsys
) -> None:
    """PROFILES-RUNTIME: profile local (interface.tui=true) passes the TUI gate at runtime."""
    ws = _workspace(tmp_path / "ws", profile="local")
    monkeypatch.chdir(ws)
    # Stub the actual TUI launch: reaching it proves the gate allowed the launch.
    import opencontext_cli.tui as tui_pkg

    monkeypatch.setattr(tui_pkg, "run_home_tui", lambda: True)

    code = handle_tui(Namespace(root=str(ws), smoke=False))

    assert code == int(ExitCode.OK)
    assert "disabled" not in capsys.readouterr().err


def test_ci_profile_makes_config_show_default_to_json(
    hermetic, tmp_path: Path, monkeypatch, capsys
) -> None:
    """CFG-004: under profile ci (interface.json_default=true), `config show`
    without --json emits JSON."""
    ws = _workspace(tmp_path / "ws", profile="ci")

    handle_config(Namespace(config_command="show", root=str(ws), json=False))

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "opencontext/config-show/v1"


def test_ci_profile_forces_non_interactive_wizard(hermetic, tmp_path: Path, monkeypatch) -> None:
    """CFG-004: under profile ci (interface.interactive=false), the config
    wizard never opens the interactive menu."""
    ws = _workspace(tmp_path / "ws", profile="ci")
    monkeypatch.chdir(ws)
    calls: dict[str, object] = {}

    import opencontext_cli.commands.menu_cmd as menu_cmd
    import opencontext_core.wizard as wizard_mod

    def _no_menu() -> None:
        raise AssertionError("interactive menu must not launch under profile ci")

    monkeypatch.setattr(menu_cmd, "run_config_menu", _no_menu)
    monkeypatch.setattr(
        wizard_mod,
        "run_wizard",
        lambda non_interactive=False: calls.setdefault("non_interactive", non_interactive),
    )

    handle_config(Namespace(config_command="wizard", non_interactive=False))

    assert calls["non_interactive"] is True


def test_local_profile_keeps_wizard_interactive(hermetic, tmp_path: Path, monkeypatch) -> None:
    """PROFILES-RUNTIME: under profile local (interface.interactive=true),
    the wizard opens the interactive menu."""
    ws = _workspace(tmp_path / "ws", profile="local")
    monkeypatch.chdir(ws)
    calls: dict[str, bool] = {}

    import opencontext_cli.commands.menu_cmd as menu_cmd
    import opencontext_core.wizard as wizard_mod

    monkeypatch.setattr(menu_cmd, "run_config_menu", lambda: calls.setdefault("menu", True))
    monkeypatch.setattr(
        wizard_mod,
        "run_wizard",
        lambda non_interactive=False: pytest.fail("non-interactive wizard must not run"),
    )

    handle_config(Namespace(config_command="wizard", non_interactive=False))

    assert calls.get("menu") is True
