"""oc-new — stateful conductor for the oc-new agentic flow.

Usage:
  opencontext oc-new start "<task>"              Start a new run
  opencontext oc-new status [--run-id ID]        Show run state
  opencontext oc-new status --watch [--run-id]   Poll state every 3s
  opencontext oc-new next [--run-id ID]          Print the next action
  opencontext oc-new done <phase>                Mark a phase complete
  opencontext oc-new resume <run_id>             Resume an interrupted run
  opencontext oc-new list                        List all runs
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.oc_new.models import OcNewRunState
from opencontext_core.oc_new.store import OcNewStore

_STATUS_ICONS = {
    "pending": "○",
    "running": "→",
    "passed": "✓",
    "warning": "⚠",
    "failed": "✗",
    "blocked": "⊘",
    "skipped": "-",
}


def _root(args: Any) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd())


def _resolve_run_id(args: Any, store: OcNewStore) -> str:
    run_id: str | None = getattr(args, "run_id", None)
    if run_id:
        return run_id
    latest = store.latest()
    if latest:
        return latest.identity.run_id
    print("No active run. Use 'opencontext oc-new start \"<task>\"'", file=sys.stderr)
    sys.exit(1)


def _print_state(state: OcNewRunState, *, json_out: bool = False) -> None:
    if json_out:
        print(state.model_dump_json(indent=2))
        return

    id_ = state.identity
    print(f"\nRun {id_.run_id} — {state.task}")
    print(f"Change: {id_.change_id}  Trace: {id_.trace_id}")
    print()
    for phase in state.phases:
        icon = _STATUS_ICONS.get(phase.status, "?")
        artifacts = ", ".join(phase.artifact_paths) if phase.artifact_paths else ""
        artifact_str = f"  [{artifacts}]" if artifacts else ""
        print(f"  {icon} {phase.name:<12} {phase.status:<10}{artifact_str}")

    print()
    if state.blocked_reason:
        print(f"Blocked: {state.blocked_reason}")
    if state.next_action:
        na = state.next_action
        print(f"Next action: {na.kind}")
        if na.phase:
            print(f"  Phase   : {na.phase}")
        if na.persona:
            print(f"  Persona : {na.persona}")
        print(f"  Instruction: {na.instruction}")
        if na.expected_artifacts:
            print(f"  Expects : {', '.join(na.expected_artifacts)}")


def _watch_state(store: OcNewStore, run_id: str, *, json_out: bool = False) -> None:
    """Poll state.json every 3 seconds, refreshing output until done or interrupted."""
    last_phase: str | None = ""
    print("Watching run state (Ctrl-C to stop)...\n")
    try:
        while True:
            try:
                state = store.load(run_id)
            except FileNotFoundError:
                print(f"Run {run_id} not found.", file=sys.stderr)
                break
            current = state.current_phase or "done"
            if current != last_phase:
                print("\033[2J\033[H", end="")  # clear screen
                _print_state(state, json_out=json_out)
                last_phase = current
            if state.next_action and state.next_action.kind == "done":
                print("\nRun complete.")
                break
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nStopped watching.")


def add_oc_new_parser(subparsers: Any) -> None:
    oc_new = subparsers.add_parser("oc-new", help="Stateful conductor for the oc-new agentic flow.")
    oc_new.add_argument("--root", default=None, help="Project root (default: cwd)")
    oc_new.add_argument("--json", dest="json_out", action="store_true", help="JSON output")
    sub = oc_new.add_subparsers(dest="oc_new_command", required=True)

    start = sub.add_parser("start", help="Start a new oc-new run.")
    start.add_argument("task", help='Task description, e.g. "add graph health command"')
    start.add_argument(
        "--flow",
        default=None,
        choices=["automatic", "stepwise", "hybrid", "engram_only", "openspec_only", "observe_only"],
        help="Flow mode controlling when the conductor pauses (default: automatic).",
    )

    status = sub.add_parser("status", help="Show current run state.")
    status.add_argument("--run-id", dest="run_id", default=None)
    status.add_argument(
        "--watch", action="store_true", help="Poll and refresh state every 3 seconds."
    )

    next_cmd = sub.add_parser("next", help="Print next action only.")
    next_cmd.add_argument("--run-id", dest="run_id", default=None)

    done = sub.add_parser("done", help="Mark a phase as complete.")
    done.add_argument("phase", help="Phase name, e.g. explore")
    done.add_argument("--run-id", dest="run_id", default=None)
    done.add_argument("--artifact", dest="artifacts", action="append", default=[], metavar="PATH")
    done.add_argument("--status", dest="done_status", default="passed",
                      choices=["passed", "warning", "failed"])

    resume = sub.add_parser("resume", help="Resume a run (re-compute next action).")
    resume.add_argument("run_id", help="Run ID to resume")

    sub.add_parser("list", help="List all oc-new runs.")


def _build_start_config(args: Any) -> Any:
    """Build an AgenticFlowConfig from CLI start args, or return None if no flags set."""
    flow_str: str | None = getattr(args, "flow", None)
    if flow_str is None:
        return None
    from opencontext_core.agentic.config import AgenticFlowConfig, FlowMode

    return AgenticFlowConfig(flow_mode=FlowMode(flow_str))


def handle_oc_new(args: Any) -> None:
    root = _root(args)
    conductor = OcNewConductor(root)
    store = OcNewStore(root)
    json_out = getattr(args, "json_out", False)
    cmd = args.oc_new_command

    if cmd == "start":
        config = _build_start_config(args)
        state = conductor.start(args.task, config=config)
        _print_state(state, json_out=json_out)

    elif cmd == "status":
        run_id = _resolve_run_id(args, store)
        watch = getattr(args, "watch", False)
        if watch:
            _watch_state(store, run_id, json_out=json_out)
        else:
            state = store.load(run_id)
            _print_state(state, json_out=json_out)

    elif cmd == "next":
        run_id = _resolve_run_id(args, store)
        state = store.load(run_id)
        if json_out:
            na = state.next_action
            print(json.dumps(na.model_dump() if na else {}, indent=2))
        else:
            na = state.next_action
            if na:
                print(f"{na.kind}: {na.instruction}")
            else:
                print("No next action.")

    elif cmd == "done":
        run_id = _resolve_run_id(args, store)
        state = conductor.mark_done(
            run_id,
            args.phase,
            status=args.done_status,
            artifact_paths=args.artifacts or None,
        )
        _print_state(state, json_out=json_out)

    elif cmd == "resume":
        state = conductor.resume(args.run_id)
        _print_state(state, json_out=json_out)

    elif cmd == "list":
        runs = store.list_runs()
        if json_out:
            print(json.dumps([r.model_dump() for r in runs], indent=2, default=str))
        else:
            if not runs:
                print("No oc-new runs found.")
                return
            for run in runs:
                phase = run.current_phase or "done"
                print(f"  {run.identity.run_id}  {phase:<14}  {run.task[:60]}")
    else:
        print(f"Unknown oc-new command: {cmd}", file=sys.stderr)
        sys.exit(1)
