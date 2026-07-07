"""Shared global-flag layer for stable commands (CLI_CONTRACT "Global flags").

``GLOBAL_FLAGS`` is the documented flag vocabulary; ``STABLE_COMMAND_FLAGS``
freezes, per stable command, the subset that parses at the command level
(``opencontext <command> [flags]``). Both are semver-protected: removing a
flag from a command is a breaking change (pinned by
``tests/cli/test_cli_flags_matrix.py``).

``--quiet`` / ``--no-color`` are the uniform output-control pair: registered
on the top-level parser (``opencontext --quiet <command>``) and, via
:func:`add_shared_output_flags`, on every stable command parser so the
trailing position (``opencontext status --quiet``) parses too. Tree-style
commands (config, memory, ...) accept them before their subcommand token;
other documented flags (``--json``, ``--root``, ``--dry-run``, ...) live on
the commands where they apply, with uniform names and semantics.
"""

from __future__ import annotations

import argparse
from typing import Final

GLOBAL_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "--json",
        "--quiet",
        "--verbose",
        "--root",
        "--config",
        "--profile",
        "--dry-run",
        "--verify",
        "--no-color",
    }
)

#: Documented per-stable-command flag subsets (top-level parse position).
STABLE_COMMAND_FLAGS: Final[dict[str, frozenset[str]]] = {
    "clean": frozenset({"--json", "--dry-run", "--quiet", "--no-color"}),
    "config": frozenset({"--quiet", "--no-color"}),
    "doctor": frozenset({"--json", "--quiet", "--no-color"}),
    "harness": frozenset({"--quiet", "--no-color"}),
    "index": frozenset({"--json", "--quiet", "--no-color"}),
    "init": frozenset({"--json", "--profile", "--quiet", "--no-color"}),
    "install": frozenset({"--json", "--dry-run", "--quiet", "--no-color"}),
    "knowledge-graph": frozenset({"--quiet", "--no-color"}),
    "memory": frozenset({"--quiet", "--no-color"}),
    "pack": frozenset({"--json", "--quiet", "--no-color"}),
    "run": frozenset({"--json", "--root", "--config", "--profile", "--quiet", "--no-color"}),
    "runs": frozenset({"--quiet", "--no-color"}),
    "sdd": frozenset({"--quiet", "--no-color"}),
    "status": frozenset({"--json", "--quiet", "--no-color"}),
    "tui": frozenset({"--quiet", "--no-color"}),
    "uninstall": frozenset({"--json", "--dry-run", "--root", "--verify", "--quiet", "--no-color"}),
    "version": frozenset({"--json", "--quiet", "--no-color"}),
}


def add_shared_output_flags(parser: argparse.ArgumentParser) -> None:
    """Register ``--quiet`` / ``--no-color`` on a stable command parser.

    ``default=argparse.SUPPRESS`` keeps the subparser from clobbering a value
    already parsed at the top level (the classic argparse namespace-overwrite
    trap), so both ``opencontext --quiet status`` and
    ``opencontext status --quiet`` resolve to ``args.quiet is True``.
    """
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Suppress human-facing progress/status output.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        dest="no_color",
        default=argparse.SUPPRESS,
        help="Disable ANSI styling.",
    )
