"""runs — inspect persisted harness runs.

Usage:
  opencontext runs list [--json]
  opencontext runs show <run_id> [--json]
  opencontext runs artifacts <run_id> [--json]

Reads the on-disk run directories the harness writes to
``.opencontext/runs/<run_id>/`` (run.json, gates.json, artifacts.json, ...),
preferring the RunStore index and falling back to a directory scan so runs
created before the index existed still appear.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from opencontext_core.harness.run_store import RunStore


def _root(args: Any) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd())


def _runs_dir(root: Path) -> Path:
    return root / ".opencontext" / "runs"


def _list_run_ids(root: Path) -> list[str]:
    """Run ids from the RunStore index, unioned with on-disk run dirs."""
    ids: set[str] = set(RunStore(root).list_run_ids())
    runs_dir = _runs_dir(root)
    if runs_dir.is_dir():
        for child in runs_dir.iterdir():
            if child.is_dir() and (child / "run.json").exists():
                ids.add(child.name)
    return sorted(ids)


def _run_dir(root: Path, run_id: str) -> Path:
    return _runs_dir(root) / run_id


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def add_run_parser(subparsers: Any) -> None:
    """Add the ``runs`` command group."""

    runs_parser = subparsers.add_parser("runs", help="Inspect persisted harness runs.")
    runs_subs = runs_parser.add_subparsers(dest="runs_action")

    list_p = runs_subs.add_parser("list", help="List persisted run IDs.")
    list_p.add_argument("--json", action="store_true", help="JSON output.")

    show_p = runs_subs.add_parser("show", help="Show a run summary.")
    show_p.add_argument("run_id", help="Run ID.")
    show_p.add_argument("--json", action="store_true", help="JSON output.")

    art_p = runs_subs.add_parser("artifacts", help="List a run's artifact files.")
    art_p.add_argument("run_id", help="Run ID.")
    art_p.add_argument("--json", action="store_true", help="JSON output.")


def handle_run_inspect(args: Any) -> None:
    """Dispatch the ``runs`` sub-command."""

    action = getattr(args, "runs_action", None)
    root = _root(args)

    if action == "list":
        ids = _list_run_ids(root)
        if getattr(args, "json", False):
            print(json.dumps(ids, indent=2))
        else:
            for rid in ids:
                print(rid)
        return

    if action == "show":
        run_dir = _run_dir(root, args.run_id)
        run_json = _read_json(run_dir / "run.json")
        if run_json is None:
            print(f"Run not found: {args.run_id}", file=sys.stderr)
            sys.exit(1)
        gates = _read_json(run_dir / "gates.json") or {}
        artifacts = _read_json(run_dir / "artifacts.json") or {}
        summary = {
            "run_id": run_json.get("run_id", args.run_id),
            "workflow": run_json.get("workflow"),
            "task": run_json.get("task"),
            "status": run_json.get("status"),
            "created_at": run_json.get("created_at"),
            "gates": len(gates.get("gates", []) if isinstance(gates, dict) else []),
            "artifacts": len(artifacts.get("artifacts", []) if isinstance(artifacts, dict) else []),
        }
        print(json.dumps(summary, indent=2))
        return

    if action == "artifacts":
        run_dir = _run_dir(root, args.run_id)
        if not run_dir.is_dir():
            print(f"Run not found: {args.run_id}", file=sys.stderr)
            sys.exit(1)
        names = sorted(p.name for p in run_dir.iterdir() if p.is_file())
        if getattr(args, "json", False):
            print(json.dumps(names, indent=2))
        else:
            for name in names:
                print(name)
        return

    print("Usage: opencontext runs [list|show|artifacts]")
    sys.exit(1)
