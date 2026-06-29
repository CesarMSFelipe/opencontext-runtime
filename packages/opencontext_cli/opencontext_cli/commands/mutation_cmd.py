"""Mutation analysis CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console


def add_mutation_commands(subparsers: argparse._SubParsersAction[Any]) -> None:
    mut = subparsers.add_parser("mutation", help="Mutation analysis operations")
    sub = mut.add_subparsers(dest="mutation_cmd")

    run_cmd = sub.add_parser("run", help="Run mutation analysis")
    run_cmd.add_argument("--scope", choices=["changed", "all"], default="changed")
    run_cmd.add_argument("--threshold", type=int, default=80)
    run_cmd.add_argument("--root", default=".")


def handle_mutation(args: argparse.Namespace, config: object = None) -> int:
    cmd = getattr(args, "mutation_cmd", None)
    if cmd == "run":
        return _handle_mutation_run(args)
    eprint("Usage: opencontext mutation run [--scope changed|all] [--threshold N]")
    return 1


def _handle_mutation_run(args: argparse.Namespace) -> int:
    try:
        from opencontext_core.mutation.runner import MutationRunner

        root = Path(getattr(args, "root", "."))
        threshold = getattr(args, "threshold", 80)
        scope = getattr(args, "scope", "changed")
        result = MutationRunner().run(root, scope=scope, threshold=threshold)

        if not result.available:
            # Not a failure — the framework is simply not installed.
            console.warning(result.error or "Mutation framework not available.")
            return 0

        passed = result.score >= threshold
        console.header("Mutation Analysis")
        console.info(f"Running mutation analysis on {scope} files...")
        console.print(
            f"Mutation coverage: {result.score:.1f}%"
            f" ({result.killed} killed, {result.survivors} survived)"
        )
        if passed:
            console.success(f"PASS — threshold met ({threshold}%)")
            return 0
        eprint(f"FAIL — threshold not met ({threshold}%)")
        return 1
    except Exception as e:
        eprint(f"Error running mutation analysis: {e}")
        return 1
