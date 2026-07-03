"""Uninstall interaction contract.

A bare ``opencontext uninstall`` on a TTY offers a navigable scope selector
(workspace / global / full) before the destructive confirm, mirroring what the
``--scope`` / ``--full`` flags encode. Non-TTY runs without ``--yes`` must not
hang or silently no-op: they exit 2 with a message (the same convention as
``config wizard --non-interactive``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

from opencontext_cli.commands.uninstall_cmd import (
    add_uninstall_parser,
    handle_uninstall,
    resolve_uninstall_scope,
)
from opencontext_core import prompts


def _parse(argv: list[str]) -> argparse.Namespace:
    root = argparse.ArgumentParser()
    subs = root.add_subparsers(dest="cmd")
    add_uninstall_parser(subs)
    return root.parse_args(["uninstall", *argv])


class _FakeStdin:
    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("OPENCONTEXT_YES", "OPENCONTEXT_JSON", "OPENCONTEXT_DRY_RUN", "OPENCONTEXT_PURGE"):
        monkeypatch.delenv(var, raising=False)


def test_scope_flag_defaults_to_none_so_interactivity_can_detect_it() -> None:
    args = _parse([])
    assert args.scope is None
    # Resolution still lands on the documented default.
    assert resolve_uninstall_scope(args) == "workspace"


def test_tty_without_scope_flags_offers_scope_select(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    args = _parse(["claude-code", "--root", str(tmp_path)])
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=True))
    calls: list[str] = []

    def fake_select(message: str, choices: object, **kwargs: object) -> str:
        calls.append(message)
        return "global"

    monkeypatch.setattr(prompts, "select", fake_select)
    monkeypatch.setattr(prompts, "confirm", lambda *a, **k: False)  # cancel before removal

    handle_uninstall(args)

    assert len(calls) == 1, "expected exactly one scope selector prompt"
    assert args.scope == "global"
    assert resolve_uninstall_scope(args) == "global"


def test_tty_scope_select_full_routes_to_full_uninstall(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    args = _parse(["claude-code", "--root", str(tmp_path)])
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=True))
    monkeypatch.setattr(prompts, "select", lambda *a, **k: "full")
    monkeypatch.setattr(prompts, "confirm", lambda *a, **k: False)  # cancel before removal

    handle_uninstall(args)

    assert args.full is True
    assert resolve_uninstall_scope(args) == "all"


def test_explicit_scope_flag_skips_the_selector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    args = _parse(["claude-code", "--scope", "workspace", "--root", str(tmp_path)])
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=True))

    def unexpected_select(*a: object, **k: object) -> str:
        raise AssertionError("scope selector must not run when --scope was given")

    monkeypatch.setattr(prompts, "select", unexpected_select)
    monkeypatch.setattr(prompts, "confirm", lambda *a, **k: False)

    handle_uninstall(args)  # must not raise


def test_non_tty_without_yes_exits_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = _parse(["claude-code", "--root", str(tmp_path)])
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=False))

    with pytest.raises(SystemExit) as excinfo:
        handle_uninstall(args)

    assert excinfo.value.code == 2
