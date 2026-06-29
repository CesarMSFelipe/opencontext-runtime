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


def _run_dirs(store: SessionStore) -> list[Path]:
    """Every run directory on disk across all sessions (best-effort)."""
    dirs: list[Path] = []
    if not store.sessions_path.is_dir():
        return dirs
    for session_dir in sorted(store.sessions_path.glob("*")):
        runs_dir = session_dir / "runs"
        if not runs_dir.is_dir():
            continue
        dirs.extend(run_dir for run_dir in sorted(runs_dir.glob("*")) if run_dir.is_dir())
    return dirs


def _decisions_for(run_dir: Path) -> list[dict[str, Any]] | None:
    """Summarized decision rows for a run directory, or ``None`` if not a run.

    A run can be persisted in two shapes: the RuntimeApi ``run.json``
    (:class:`RuntimeRun` with a ``decision_log``) or the OC Flow run, which
    writes ``decisions.json`` (already summarized) plus ``state.json``. Returns
    ``[]`` for a real run that recorded no decisions, and ``None`` only when
    ``run_dir`` is not a recognizable run at all.
    """
    run_json = run_dir / "run.json"
    if run_json.exists():
        try:
            run = RuntimeRun.model_validate_json(run_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return summarize_decision_log(run.decision_log)

    decisions_json = run_dir / "decisions.json"
    if decisions_json.exists():
        try:
            payload = json.loads(decisions_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        rows = payload.get("decisions") if isinstance(payload, dict) else None
        return list(rows) if isinstance(rows, list) else []

    # An OC Flow run dir is marked by state.json even when no decisions exist.
    if (run_dir / "state.json").exists():
        return []
    return None


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
        rows: list[dict[str, Any]] = []
        for run_dir in _run_dirs(store):
            decisions = _decisions_for(run_dir)
            if decisions:  # only runs that actually recorded decisions
                rows.append({"run_id": run_dir.name, "decisions": len(decisions)})
        if getattr(args, "json", False):
            print(json.dumps(rows, indent=2))
        elif rows:
            for row in rows:
                print(f"{row['run_id']}\t{row['decisions']} decisions")
        else:
            print("No runs with recorded decisions yet.")
        return

    if action == "show":
        run_dir = next((d for d in _run_dirs(store) if d.name == args.run_id), None)
        if run_dir is None:
            print(f"Run not found: {args.run_id}", file=sys.stderr)
            sys.exit(1)
        decision_rows = _decisions_for(run_dir) or []
        if getattr(args, "json", False):
            print(json.dumps(decision_rows, indent=2))
        else:
            if not decision_rows:
                # The run exists; it simply has no decisions (RI/decision-log off
                # or the run produced none). Honest, not "Run not found".
                print(
                    f"Run {args.run_id}: no decisions recorded "
                    "(runtime decision-log produced none)."
                )
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
