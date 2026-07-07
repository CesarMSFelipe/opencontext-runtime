"""SDD-CMDS: every change-taking sdd verb accepts the change name positionally.

Pins the CLI-surface coherence rule: `sdd new demo` and `sdd status demo`
must both work (the positional was previously wired only for new/review).
"""

from __future__ import annotations

import argparse

import pytest

from opencontext_cli.commands.sdd_cmd import add_sdd_parser

CHANGE_VERBS = [
    "new",
    "status",
    "continue",
    "propose",
    "spec",
    "design",
    "tasks",
    "apply",
    "verify",
    "review",
    "archive",
    "ff",
]


def _parse(argv: list[str]) -> argparse.Namespace:
    root = argparse.ArgumentParser(prog="opencontext")
    sub = root.add_subparsers(dest="command")
    add_sdd_parser(sub)
    return root.parse_args(argv)


@pytest.mark.parametrize("verb", CHANGE_VERBS)
def test_positional_change_accepted(verb: str) -> None:
    args = _parse(["sdd", verb, "demo-change", "--cwd", "."])
    assert getattr(args, "change", None) == "demo-change"


@pytest.mark.parametrize("verb", CHANGE_VERBS)
def test_change_flag_survives_absent_positional(verb: str) -> None:
    args = _parse(["sdd", verb, "--change", "flag-change", "--cwd", "."])
    assert getattr(args, "change", None) == "flag-change"
