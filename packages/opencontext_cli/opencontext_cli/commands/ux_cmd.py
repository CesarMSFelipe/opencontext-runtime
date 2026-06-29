"""UX façade — ``opencontext workflow {start,status,approve,receipt}``.

Thin handlers that delegate ONE hop to the existing ``OcNewConductor``,
``OcNewStore``, and ``AgenticReceipt`` machinery. No orchestration logic.

Namespace decision (design.md D1): mounted under the existing ``workflow``
subparser to avoid colliding with top-level ``status`` (main.py:1175) and
``approvals approve`` (main.py:1080).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core.agentic.receipt import AgenticReceipt
from opencontext_core.dx.console_styles import console
from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.oc_new.store import OcNewStore
from opencontext_core.workflow.state import WorkflowState

_APPROVAL_BASENAME = "approval.json"


def _root(args: Any) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd())


def _resolve_run_id(args: Any, store: OcNewStore) -> str:
    run_id: Any = getattr(args, "run_id", None)
    if run_id:
        return str(run_id)
    latest = store.latest()
    if latest is None:
        eprint("No active run. Use 'opencontext workflow start <task>'.")
        sys.exit(1)
    return latest.identity.run_id


def _print_workflow_state(
    state: WorkflowState, *, json_out: bool, title: str = "Workflow Run"
) -> None:
    if json_out:
        print(state.model_dump_json(indent=2))
        return
    console.header(title)
    console.print(f"Run     : {state.run_id}")
    console.print(f"Change  : {state.change_id}")
    console.print(f"Trace   : {state.trace_id}")
    console.print(f"Task    : {state.task}")
    console.print(f"Current : {state.current_phase or 'done'}")
    console.print(f"Next    : {state.next_action_kind or '-'}")
    if state.blocked_reason:
        console.warning(f"Blocked: {state.blocked_reason}")
    console.table(
        "Phases",
        ["Phase", "Status"],
        [[phase.name, phase.status] for phase in state.phases],
    )


# Handlers — each MUST be a one-hop delegation to the existing spine.


def _handle_start(args: Any) -> None:
    root = _root(args)
    state = OcNewConductor(root).start(args.task)
    _print_workflow_state(
        WorkflowState.project_from(state),
        json_out=getattr(args, "json_out", False),
        title="Workflow Started",
    )


def _handle_status(args: Any) -> None:
    root = _root(args)
    store = OcNewStore(root)
    run_id = _resolve_run_id(args, store)
    state = store.load(run_id)
    _print_workflow_state(
        WorkflowState.project_from(state),
        json_out=getattr(args, "json_out", False),
        title="Workflow Status",
    )


def _handle_approve(args: Any) -> None:
    """Write run-dir approval.json then delegate the re-advance to the conductor.

    Side effect is a single file write scoped to the run dir; no new state,
    no third spine. The conductor's own _validate_approval_content accepts the
    shape we write, so the next advance() proceeds past the approval gate.
    """
    root = _root(args)
    store = OcNewStore(root)
    run_id = _resolve_run_id(args, store)
    run_dir = store.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / _APPROVAL_BASENAME).write_text(
        json.dumps(
            {
                "status": "approved",
                "approved": True,
                "approved_at": datetime.now(tz=UTC).isoformat(),
                "approver": getattr(args, "approver", None) or "workflow-cli",
                "note": getattr(args, "note", None) or "",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    state = OcNewConductor(root).resume(run_id)
    _print_workflow_state(
        WorkflowState.project_from(state),
        json_out=getattr(args, "json_out", False),
        title="Workflow Approved",
    )


def _handle_receipt(args: Any) -> None:
    """Render the AgenticReceipt for the requested run (one read, no mutation)."""
    root = _root(args)
    store = OcNewStore(root)
    run_id = _resolve_run_id(args, store)
    receipt_path = store.run_dir(run_id) / "receipt.json"
    if not receipt_path.exists():
        eprint(f"No receipt at {receipt_path}")
        sys.exit(1)
    receipt = AgenticReceipt.model_validate_json(receipt_path.read_text())
    if getattr(args, "json_out", False):
        print(receipt.model_dump_json(indent=2))
        return
    console.header("Workflow Receipt")
    console.print(f"Receipt   : {receipt.run_id}")
    console.print(f"Change    : {receipt.change_id}")
    console.print(f"Status    : {receipt.status}")
    console.print(f"Flow      : {receipt.flow_mode}")
    console.print(f"Completed : {', '.join(receipt.completed_phases) or '-'}")
    if receipt.failed_phases:
        console.error(f"Failed    : {', '.join(receipt.failed_phases)}")
    if receipt.warnings:
        console.warning(f"Warnings  : {len(receipt.warnings)}")


def add_workflow_ux_parser(workflow_subparsers: Any) -> None:
    """Mount the four UX verbs onto the existing ``workflow`` subparsers."""

    start_p = workflow_subparsers.add_parser(
        "start", help="Start a new agentic run (thin façade over OcNewConductor.start)."
    )
    start_p.add_argument("task", help='Task description, e.g. "add graph health command"')
    start_p.add_argument("--root", default=None, help="Project root (default: cwd).")
    start_p.add_argument("--json", dest="json_out", action="store_true", help="JSON output.")

    status_p = workflow_subparsers.add_parser(
        "status", help="Show a projected WorkflowState for a run (read-only)."
    )
    status_p.add_argument("--run-id", dest="run_id", default=None, help="Run ID to inspect.")
    status_p.add_argument("--root", default=None, help="Project root (default: cwd).")
    status_p.add_argument("--json", dest="json_out", action="store_true", help="JSON output.")

    approve_p = workflow_subparsers.add_parser(
        "approve", help="Mark the approval gate approved and re-advance the run."
    )
    approve_p.add_argument(
        "--run-id", dest="run_id", default=None, help="Run ID to approve (default: latest)."
    )
    approve_p.add_argument("--root", default=None, help="Project root (default: cwd).")
    approve_p.add_argument(
        "--approver", default=None, help="Optional identifier recorded in approval.json."
    )
    approve_p.add_argument("--note", default=None, help="Optional note recorded in approval.json.")
    approve_p.add_argument("--json", dest="json_out", action="store_true", help="JSON output.")

    receipt_p = workflow_subparsers.add_parser(
        "receipt", help="Show the AgenticReceipt for a completed run."
    )
    receipt_p.add_argument(
        "--run-id", dest="run_id", default=None, help="Run ID to inspect (default: latest)."
    )
    receipt_p.add_argument("--root", default=None, help="Project root (default: cwd).")
    receipt_p.add_argument("--json", dest="json_out", action="store_true", help="JSON output.")

    explain_p = workflow_subparsers.add_parser(
        "explain", help="Explain a workflow (when/when-not/cost/phases/harnesses)."
    )
    explain_p.add_argument("workflow", help="Workflow id, e.g. 'sdd' or 'oc-flow'.")
    explain_p.add_argument("--root", default=None, help="Project root (default: cwd).")
    explain_p.add_argument("--json", dest="json_out", action="store_true", help="JSON output.")


def _handle_explain(args: Any) -> None:
    """Explain a workflow via the shared explain logic (SPEC-CLI-013-10)."""
    from opencontext_core.explain import explain_workflow

    info = explain_workflow(str(getattr(args, "workflow", "")), str(_root(args)))
    if getattr(args, "json_out", False):
        print(json.dumps(info, indent=2))
        if "error" in info:
            sys.exit(1)
        return
    if "error" in info:
        eprint(str(info["error"]))
        if info.get("next_action"):
            console.dim(f"  {info['next_action']}")
        sys.exit(1)
    console.header(f"Workflow: {info['id']}")
    console.print(f"When      : {info['when']}")
    console.print(f"When not  : {info['when_not']}")
    console.print(f"Cost      : {info['cost']}")
    console.print(f"Risk      : {info['risk']}")
    console.print(f"Phases    : {', '.join(info['phases']) or '-'}")
    console.print(f"Harnesses : {', '.join(info['harnesses']) or '-'}")
    if info["outputs"]:
        console.print(f"Outputs   : {', '.join(info['outputs'])}")


def handle_workflow_ux(args: Any) -> None:
    """Dispatch one of the four UX verbs."""
    cmd = getattr(args, "workflow_command", None)
    if cmd == "start":
        _handle_start(args)
    elif cmd == "status":
        _handle_status(args)
    elif cmd == "approve":
        _handle_approve(args)
    elif cmd == "receipt":
        _handle_receipt(args)
    elif cmd == "explain":
        _handle_explain(args)
    else:
        eprint(f"Unknown workflow subcommand: {cmd}")
        sys.exit(2)
