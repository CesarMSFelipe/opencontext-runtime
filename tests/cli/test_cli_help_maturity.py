"""CLI-EXP-HIDDEN: primary --help visibility matches the command maturity registry.

PRODUCT_CONTRACT freeze: internal commands are hidden from the primary
``opencontext --help``; preview/internal commands must not be presented as
stable in the main help. Stable commands must all be listed.
"""

from __future__ import annotations

import argparse
import re

from opencontext_cli.contracts.command_registry import COMMAND_MATURITY
from opencontext_cli.main import _COMMAND_GROUPS_EPILOG, _build_parser


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))


def _visible_entries() -> dict[str, str]:
    """Command -> help text for entries the primary help will list."""
    action = _subparsers_action(_build_parser())
    return {
        pseudo.dest: str(pseudo.help or "")
        for pseudo in action._choices_actions
        if pseudo.help != argparse.SUPPRESS
    }


def _rendered_command_lines() -> set[str]:
    """First tokens of the 4-space-indented choice lines in the rendered help."""
    help_text = _build_parser().format_help()
    names: set[str] = set()
    for line in help_text.splitlines():
        match = re.match(r"^ {2,6}([a-z][a-z0-9-]*)\b", line)
        if match:
            names.add(match.group(1))
    return names


def test_internal_commands_hidden_from_primary_help() -> None:
    """CLI-EXP-HIDDEN: no internal command is listed in the primary --help."""
    internal = {cmd for cmd, level in COMMAND_MATURITY.items() if level == "internal"}
    visible = set(_visible_entries())
    leaked = sorted(internal & visible)
    assert not leaked, f"internal commands leaked into primary help: {leaked}"
    rendered_leaks = sorted(internal & _rendered_command_lines())
    assert not rendered_leaks, f"internal commands rendered in --help text: {rendered_leaks}"


def test_stable_commands_listed_in_primary_help() -> None:
    """CLI-EXP-HIDDEN: every stable command (including init) is listed in --help."""
    stable = {cmd for cmd, level in COMMAND_MATURITY.items() if level == "stable"}
    visible = set(_visible_entries())
    missing = sorted(stable - visible)
    assert not missing, f"stable commands missing from primary help: {missing}"
    rendered = _rendered_command_lines()
    unrendered = sorted(stable - rendered)
    assert not unrendered, f"stable commands not rendered in --help text: {unrendered}"


def test_visible_preview_commands_carry_preview_marker() -> None:
    """CLI-EXP-HIDDEN: listed preview commands are tagged, never presented as stable."""
    unmarked = sorted(
        cmd
        for cmd, help_text in _visible_entries().items()
        if COMMAND_MATURITY.get(cmd, "preview") == "preview" and "preview" not in help_text
    )
    assert not unmarked, f"preview commands presented without a preview marker: {unmarked}"


def test_help_epilog_routes_name_no_internal_commands() -> None:
    """CLI-EXP-HIDDEN: the command-routes epilog promotes no internal command."""
    internal = {cmd for cmd, level in COMMAND_MATURITY.items() if level == "internal"}
    mentioned = {
        token.strip().rstrip(",")
        for line in _COMMAND_GROUPS_EPILOG.splitlines()
        for token in line.split()[1:]  # drop the route/category label
        if line.startswith("  ")
    }
    promoted = sorted(internal & mentioned)
    assert not promoted, f"epilog promotes internal commands: {promoted}"
