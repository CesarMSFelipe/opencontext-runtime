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


def test_envelope_prepends_schema_discriminator() -> None:
    from opencontext_cli.output import envelope

    out = envelope("x.v1", {"a": 1})
    assert out == {"schema": "x.v1", "a": 1}
    # schema wins on collision — the discriminator is authoritative.
    assert envelope("x.v1", {"schema": "spoofed"})["schema"] == "x.v1"


def test_maturity_commands_json_carries_schema(capsys) -> None:
    """`maturity commands --json` joins the schema-keyed machine-facing family."""
    import json
    from types import SimpleNamespace

    from opencontext_cli.commands.maturity_cmd import handle_maturity

    handle_maturity(SimpleNamespace(maturity_command="commands", json=True, output=None))
    data = json.loads(capsys.readouterr().out.strip())
    assert data["schema"] == "maturity.commands.v1"
    assert set(data["by_level"]) == {"stable", "preview", "internal"}
