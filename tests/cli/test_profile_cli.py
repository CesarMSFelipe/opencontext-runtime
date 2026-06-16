"""SDD model-profile CLI: create/set/show/delete round-trip, isolated from $HOME."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from opencontext_cli.commands import profile_cmd
from opencontext_core.sdd_profiles import SDDProfileManager


@pytest.fixture(autouse=True)
def _isolated_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # handle_profile builds SDDProfileManager() internally; redirect it to tmp so
    # the test never touches the real ~/.config/opencontext/profiles.
    monkeypatch.setattr(profile_cmd, "SDDProfileManager", lambda: SDDProfileManager(tmp_path))


def _run(**kwargs) -> int:
    return profile_cmd.handle_profile(Namespace(**kwargs))


def test_create_set_show_delete_round_trip(capsys) -> None:
    assert _run(profile_command="create", name="mine", description="", base="hybrid") == 0
    # The created profile inherited the base's assignments.
    _run(profile_command="show", name="mine", json=True)
    assert '"design"' in capsys.readouterr().out

    # Override a single phase.
    assert _run(profile_command="set", name="mine", phase="apply", model="gpt-5") == 0
    _run(profile_command="show", name="mine", json=True)
    assert '"apply": "gpt-5"' in capsys.readouterr().out

    assert _run(profile_command="delete", name="mine") == 0


def test_create_from_unknown_base_fails() -> None:
    assert _run(profile_command="create", name="x", description="", base="nope") == 1


def test_set_on_missing_profile_fails() -> None:
    assert _run(profile_command="set", name="ghost", phase="apply", model="m") == 1


def test_cannot_delete_builtin() -> None:
    assert _run(profile_command="delete", name="hybrid") == 1


def test_list_includes_builtins(capsys) -> None:
    assert _run(profile_command="list") == 0
    out = capsys.readouterr().out
    assert "hybrid" in out and "cheap" in out
