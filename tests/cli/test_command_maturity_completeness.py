"""Every registered top-level CLI command must declare an API-maturity level.

Regression: the maturity map was hand-maintained and drifted from the parser —
new commands shipped without a stable/preview/internal classification, so
`opencontext maturity commands` under-reported the surface. This asserts the map
covers exactly the registered commands (including aliases), no more, no less.
"""

from __future__ import annotations

import argparse

from opencontext_cli.command_maturity import COMMAND_MATURITY, MATURITIES
from opencontext_cli.main import _build_parser


def _registered_commands() -> set[str]:
    parser = _build_parser()
    names: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            names.update(action.choices.keys())
    return names


def test_every_registered_command_has_a_maturity() -> None:
    registered = _registered_commands()
    missing = sorted(registered - set(COMMAND_MATURITY))
    assert not missing, f"commands missing a maturity classification: {missing}"


def test_no_stale_maturity_entries() -> None:
    registered = _registered_commands()
    stale = sorted(set(COMMAND_MATURITY) - registered)
    assert not stale, f"maturity entries for unregistered commands: {stale}"


def test_all_maturity_values_are_valid() -> None:
    invalid = {c: lvl for c, lvl in COMMAND_MATURITY.items() if lvl not in MATURITIES}
    assert not invalid, f"invalid maturity levels: {invalid}"
