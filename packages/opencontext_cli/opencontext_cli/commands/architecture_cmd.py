"""``opencontext architecture`` — architecture governance tooling (PROD-005 / B5).

``architecture diff`` snapshots the live versioned contracts and cross-package
dependency edges and diffs them against the frozen baseline
(``tests/architecture/architecture-baseline.json``). It is the human/CI surface over
:mod:`opencontext_core.compat.architecture_diff`:

* ``--json`` emits a pure machine-readable diff to stdout (CI gate);
* the human render uses the brand console.

Exit code is ``0`` when the live state matches the baseline and ``1`` when drift is
detected, so the command doubles as a release gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from opencontext_cli.output import eprint

_DEFAULT_BASELINE = "tests/architecture/architecture-baseline.json"


def add_architecture_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    """Register the ADDITIVE ``architecture`` subparser (1.0 CLI surface guard)."""
    arch = subparsers.add_parser("architecture", help="Architecture governance tooling.")
    sub = arch.add_subparsers(dest="architecture_command")

    diff_p = sub.add_parser(
        "diff", help="Diff live contracts/dependencies vs the architecture baseline."
    )
    diff_p.add_argument(
        "--baseline",
        default=None,
        help=f"Path to the architecture baseline JSON (default: {_DEFAULT_BASELINE}).",
    )
    diff_p.add_argument("--json", action="store_true", help="Emit pure JSON to stdout.")


def handle_architecture(args: argparse.Namespace) -> int:
    cmd = getattr(args, "architecture_command", None)
    if cmd == "diff":
        return _handle_diff(args)
    eprint("Usage: opencontext architecture diff [--baseline PATH] [--json]")
    return 1


def _resolve_baseline(args: argparse.Namespace) -> Path:
    raw = getattr(args, "baseline", None)
    return Path(raw) if raw else Path.cwd() / _DEFAULT_BASELINE


def _handle_diff(args: argparse.Namespace) -> int:
    from opencontext_core.compat.architecture_diff import current_snapshot, diff, load_baseline

    baseline_path = _resolve_baseline(args)
    if not baseline_path.is_file():
        eprint(f"Architecture baseline not found: {baseline_path}")
        return 2

    result = diff(load_baseline(baseline_path), current_snapshot())

    if getattr(args, "json", False):
        payload = {**result.model_dump(), "drift": result.has_drift}
        print(json.dumps(payload, indent=2, sort_keys=True))  # pure JSON to stdout
        return 1 if result.has_drift else 0

    _render_human(result, baseline_path)
    return 1 if result.has_drift else 0


def _render_human(result: Any, baseline_path: Path) -> None:
    from opencontext_core.dx.console_styles import console

    console.header("Architecture Diff")
    console.print(f"[dim]baseline: {baseline_path}[/]")
    if not result.has_drift:
        console.success("No architecture drift — live contracts and dependencies match baseline.")
        return

    sections = (
        ("Added contracts", result.added_contracts),
        ("Removed contracts", result.removed_contracts),
        ("Changed contracts", result.changed_contracts),
        ("Added dependencies", result.added_dependencies),
        ("Removed dependencies", result.removed_dependencies),
    )
    for title, items in sections:
        if not items:
            continue
        console.section(title)
        for item in items:
            console.print(f"  - {item}")
    console.warning(
        "Architecture drift detected — bump the affected schema_version(s) and "
        "regenerate architecture-baseline.json in the same change."
    )
