"""decisions — inspect a run's Runtime Brain Decision Log (RB-009).

Usage:
  opencontext decisions list [--json]
  opencontext decisions show <run_id> [--json]

Surfaces the advisory Runtime Brain decisions recorded for a run: each
decision's kind, selected value, alternatives, and rationale. Reads the
RuntimeApi session store at ``.opencontext/sessions/<session>/runs/<run>/run.json``
(the Decision Log is attached to the run). Adaptive-but-not-opaque: the Brain
recommends, the State Machine governs, and every choice is inspectable here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from opencontext_core.runtime.decisions import summarize_decision_log
from opencontext_core.runtime.run import RuntimeRun
from opencontext_core.runtime.session_store import SessionStore


def _root(args: Any) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd())


def _iter_runs(store: SessionStore) -> list[RuntimeRun]:
    """Load every persisted run across all sessions (best-effort)."""
    runs: list[RuntimeRun] = []
    if not store.sessions_path.is_dir():
        return runs
    for session_dir in sorted(store.sessions_path.glob("*")):
        runs_dir = session_dir / "runs"
        if not runs_dir.is_dir():
            continue
        for run_dir in sorted(runs_dir.glob("*")):
            run_json = run_dir / "run.json"
            if not run_json.exists():
                continue
            try:
                runs.append(RuntimeRun.model_validate_json(run_json.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return runs


def add_decisions_parser(subparsers: Any) -> None:
    """Add the ``decisions`` command group."""
    decisions_parser = subparsers.add_parser(
        "decisions", help="Inspect a run's Runtime Brain Decision Log."
    )
    decisions_subs = decisions_parser.add_subparsers(dest="decisions_action")

    list_p = decisions_subs.add_parser("list", help="List runs that have recorded decisions.")
    list_p.add_argument("--json", action="store_true", help="JSON output.")

    show_p = decisions_subs.add_parser("show", help="Show a run's recorded decisions.")
    show_p.add_argument("run_id", help="Run ID.")
    show_p.add_argument("--json", action="store_true", help="JSON output.")


def handle_decisions(args: Any) -> None:
    """Dispatch the ``decisions`` sub-command."""
    action = getattr(args, "decisions_action", None)
    store = SessionStore(_root(args))

    if action == "list":
        rows = [
            {"run_id": run.run_id, "decisions": len(run.decision_log)}
            for run in _iter_runs(store)
            if len(run.decision_log) > 0
        ]
        if getattr(args, "json", False):
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                print(f"{row['run_id']}\t{row['decisions']} decisions")
        return

    if action == "show":
        run = next((r for r in _iter_runs(store) if r.run_id == args.run_id), None)
        if run is None:
            print(f"Run not found: {args.run_id}", file=sys.stderr)
            sys.exit(1)
        decision_rows = summarize_decision_log(run.decision_log)
        if getattr(args, "json", False):
            print(json.dumps(decision_rows, indent=2))
        else:
            if not decision_rows:
                print(f"No decisions recorded for run {args.run_id}.")
                return
            for drow in decision_rows:
                governed = f" [governed_by={drow['governed_by']}]" if drow["governed_by"] else ""
                print(f"- {drow['kind']}: {drow['selected']}{governed}")
                if drow["rationale"]:
                    print(f"    rationale: {drow['rationale']}")
                if drow["alternatives"]:
                    print(f"    alternatives: {', '.join(drow['alternatives'])}")
        return

    print("Usage: opencontext decisions [list|show]")
    sys.exit(1)
