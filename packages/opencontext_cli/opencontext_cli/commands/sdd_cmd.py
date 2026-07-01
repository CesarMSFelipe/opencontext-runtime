"""SDD CLI commands: opencontext sdd {verb} namespace with 15 verbs.

Per openspec/changes/agentic-parity-engram-gentle/design/pr3-cli-fastapi.md:

* ``add_sdd_parser(sub)`` registers the ``sdd`` subcommand with 15 verbs.
* ``handle_sdd(args)`` dispatches each verb to its handler — phase verbs
  delegate to :func:`opencontext_sdd.runner.run_phase` when available;
  ``status`` calls :func:`opencontext_sdd.status.Resolve` directly.

LB 2026 — SDD orchestrator CLI surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SUBCOMMANDS = [
    "init",
    "new",
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "apply",
    "verify",
    "archive",
    "status",
    "continue",
    "ff",
    "onboard",
    "list",
]

_PHASE_VERBS = {"init", "new", "explore", "propose", "spec", "design",
                 "tasks", "apply", "verify", "archive"}
_STATUS_VERBS = {"status", "continue", "ff", "onboard", "list"}


def add_sdd_parser(subparsers: Any) -> argparse.ArgumentParser:
    """Register the ``opencontext sdd`` subcommand with all 15 verbs.

    Returns the sdd parser for test introspection.
    """
    sdd_parser = subparsers.add_parser(
        "sdd",
        help="Spec-Driven Development workflow commands.",
        description=(
            "Manage SDD changes through the full lifecycle: init, new, explore, "
            "propose, spec, design, tasks, apply, verify, archive, status, "
            "continue, ff (fast-forward), onboard, list."
        ),
    )
    sdd_sub = sdd_parser.add_subparsers(dest="sdd_command", required=True)

    for verb in SUBCOMMANDS:
        p = sdd_sub.add_parser(verb, help=_verb_help(verb))
        p.add_argument("--cwd", default=".", help="Project root (default: current dir).")
        p.add_argument("--verbose", action="store_true", help="Verbose output.")

        if verb in {"new", "status", "continue", "propose", "spec", "design",
                     "tasks", "apply", "verify", "archive", "ff"}:
            p.add_argument("--change", default=None, help="Change name.")
            if verb == "new":
                p.add_argument("change", nargs="?", help="Change name (positional).")

        if verb == "explore":
            p.add_argument("--topic", default=None, help="Exploration topic.")

        if verb == "apply":
            p.add_argument("--task", default=None, help="Task ID to apply (e.g. T3.1).")

    return sdd_parser


def handle_sdd(args: Any) -> None:
    """Dispatch ``args.sdd_command`` to the appropriate handler."""
    verb = args.sdd_command
    cwd = Path(getattr(args, "cwd", ".")).resolve()
    change = getattr(args, "change", None)
    topic = getattr(args, "topic", None)
    task = getattr(args, "task", None)
    verbose = getattr(args, "verbose", False)

    # Phase verbs delegate to run_phase (stub until PR4.a ships runner.py)
    if verb in _PHASE_VERBS:
        _run_phase(verb, cwd, change, topic=topic, task=task, verbose=verbose)
        return

    # Status-family verbs
    if verb == "status":
        _handle_status(change, cwd, verbose)
        return
    if verb == "continue":
        _handle_continue(change, cwd, verbose)
        return
    if verb == "ff":
        _handle_ff(change, cwd, verbose)
        return
    if verb == "onboard":
        _handle_onboard(cwd, verbose)
        return
    if verb == "list":
        _handle_list(cwd, verbose)
        return

    _unreachable(verb)


# ---------------------------------------------------------------------------
# Handlers (thin wrappers — real logic lives in opencontext_sdd.*)
# ---------------------------------------------------------------------------


def _handle_status(change: str | None, cwd: Path, verbose: bool) -> None:
    """Resolve and print the SDD status."""
    from opencontext_sdd.status import Resolve, Status

    status = Resolve(change or "", str(cwd))
    _print_json(status.model_dump(mode="json", exclude_none=True), verbose)


def _handle_continue(change: str | None, cwd: Path, verbose: bool) -> None:
    """Continue with the next recommeded phase."""
    from opencontext_sdd.dispatcher import RenderNativePhasePrompt

    prompt = RenderNativePhasePrompt(change or "", str(cwd))
    print(prompt)


def _handle_ff(change: str | None, cwd: Path, verbose: bool) -> None:
    """Fast-forward: proposal → spec → design → tasks."""
    print(f"Fast-forward planning for change '{change}' at {cwd}.")
    print("(run_phase wiring ships in PR4 — placeholder)")


def _handle_onboard(cwd: Path, verbose: bool) -> None:
    """Walk user through the SDD cycle."""
    print(f"SDD onboarding at {cwd}.")
    print("(onboard handler ships in PR4 — placeholder)")


def _handle_list(cwd: Path, verbose: bool) -> None:
    """List active changes."""
    changes_dir = cwd / "openspec" / "changes"
    if changes_dir.is_dir():
        for child in sorted(changes_dir.iterdir()):
            if child.is_dir():
                print(f"  {child.name}")
    else:
        print("  (no active changes)")


def _run_phase(
    verb: str,
    cwd: Path,
    change: str | None,
    *,
    topic: str | None = None,
    task: str | None = None,
    verbose: bool = False,
) -> None:
    """Run an SDD phase via the orchestrator runner."""
    # PR4.a replaces this with runner.run_phase()
    parts = [f"Running phase '{verb}'"]
    if change:
        parts.append(f"change={change}")
    if topic:
        parts.append(f"topic={topic}")
    if task:
        parts.append(f"task={task}")
    parts.append(f"cwd={cwd}")
    print(" ".join(parts))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verb_help(verb: str) -> str:
    """Short help line for each verb."""
    HELP = {
        "init": "Bootstrap SDD context for the project.",
        "new": "Start a new SDD change.",
        "explore": "Explore an idea or requirement.",
        "propose": "Create a change proposal.",
        "spec": "Write detailed specs from the proposal.",
        "design": "Create technical design from specs.",
        "tasks": "Break design into implementation tasks.",
        "apply": "Implement tasks from specs and design.",
        "verify": "Validate implementation against specs.",
        "archive": "Archive a completed change.",
        "status": "Show structured status for the active change.",
        "continue": "Run the next dependency-ready phase.",
        "ff": "Fast-forward planning (proposal→spec→design→tasks).",
        "onboard": "Walk through SDD on the real codebase.",
        "list": "List active changes.",
    }
    return HELP.get(verb, verb.title())


def _print_json(data: Any, verbose: bool) -> None:
    """Pretty-print JSON to stdout."""
    json.dump(data, sys.stdout, indent=2, default=str)
    print()


def _unreachable(verb: str) -> None:
    raise SystemExit(f"Unreachable: unknown sdd verb '{verb}'")
