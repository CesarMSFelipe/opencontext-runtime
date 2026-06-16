"""Mutation analysis CLI commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def add_mutation_commands(subparsers: argparse._SubParsersAction) -> None:
    mut = subparsers.add_parser("mutation", help="Mutation analysis operations")
    sub = mut.add_subparsers(dest="mutation_cmd")

    run_cmd = sub.add_parser("run", help="Run mutation analysis")
    run_cmd.add_argument("--scope", choices=["changed", "all"], default="changed")
    run_cmd.add_argument("--threshold", type=int, default=80)
    run_cmd.add_argument("--root", default=".")


def handle_mutation(args: argparse.Namespace, config=None) -> int:
    cmd = getattr(args, "mutation_cmd", None)
    if cmd == "run":
        return _handle_mutation_run(args)
    print("Usage: opencontext mutation run [--scope changed|all] [--threshold N]", file=sys.stderr)
    return 1


def _handle_mutation_run(args: argparse.Namespace) -> int:
    try:
        from opencontext_core.mutation.runner import MutationRunner

        root = Path(getattr(args, "root", "."))
        threshold = getattr(args, "threshold", 80)
        scope = getattr(args, "scope", "changed")
        result = MutationRunner().run(root, scope=scope, threshold=threshold)

        if not result.available:
            print(f"Warning: {result.error}")
            return 0  # Not a failure — framework just not installed

        status = "PASS" if result.score >= threshold else "FAIL"
        threshold_label = "met" if result.score >= threshold else "not met"
        print(f"Running mutation analysis on {args.scope} files...")
        print(
            f"Mutation coverage: {result.score:.1f}%"
            f" ({result.killed} killed, {result.survivors} survived)"
        )
        print(f"{status} Threshold {threshold_label} ({threshold}%)")
        return 0 if result.score >= threshold else 1
    except Exception as e:
        print(f"Error running mutation analysis: {e}", file=sys.stderr)
        return 1
