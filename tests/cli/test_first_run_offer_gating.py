"""The first-run wizard offer must never fire for machine/no-prompt invocations.

A pty-allocated CI or agent session still has a TTY on stdout, so gating the
offer on ``isatty`` alone is not enough: ``--json`` output must stay pure and
``--yes`` / ``--non-interactive`` runs must never block on a confirm prompt.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from opencontext_cli import main as cli_main


def _args(**flags: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "json": False,
        "json_out": False,
        "yes": False,
        "non_interactive": False,
    }
    base.update(flags)
    return SimpleNamespace(**base)


def _run_check(args: SimpleNamespace) -> bool:
    """Invoke the first-run check as a first-run TTY session; report whether
    the interactive offer (prompts.confirm) was reached."""
    asked: list[str] = []

    def _fake_confirm(message: str, *, default: bool = True) -> bool:
        asked.append(message)
        return False

    with (
        patch.object(cli_main, "is_first_run", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("opencontext_core.prompts.confirm", _fake_confirm),
    ):
        cli_main._check_first_run("run", args)
    return bool(asked)


def test_offer_skipped_for_json() -> None:
    assert _run_check(_args(json=True)) is False


def test_offer_skipped_for_json_out() -> None:
    assert _run_check(_args(json_out=True)) is False


def test_offer_skipped_for_yes() -> None:
    assert _run_check(_args(yes=True)) is False


def test_offer_skipped_for_non_interactive() -> None:
    assert _run_check(_args(non_interactive=True)) is False


def test_offer_still_fires_interactively() -> None:
    assert _run_check(_args()) is True
