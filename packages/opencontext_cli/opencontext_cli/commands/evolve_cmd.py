"""``opencontext evolve`` — manage propose-only evolution proposals.

Subcommands:
  proposals           List all evolution proposals from the EvolutionStore.
  approve <id>        Mark a proposal as approved (does NOT auto-apply it).
  reject <id>         Mark a proposal as rejected.

Evolution proposals are generated automatically after harness runs (when
``learning.in_loop`` is enabled) and stored in
``.opencontext/learning/evolution/``.  This CLI lets you review and approve
or reject them.  Approving a proposal records human sign-off — it does NOT
apply any configuration change automatically.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console

if TYPE_CHECKING:
    from opencontext_core.learning.evolution_store import EvolutionStore


def add_evolve_parser(subparsers: Any) -> None:
    """Register the ``evolve`` command group."""
    evolve_parser = subparsers.add_parser(
        "evolve",
        help="Manage evolution proposals.",
        description=(
            "List, approve, or reject propose-only evolution signals generated "
            "from harness run evidence. Approving a proposal records human sign-off "
            "but does NOT auto-apply configuration changes."
        ),
    )
    evolve_sub = evolve_parser.add_subparsers(dest="evolve_command", required=True)

    # proposals
    proposals_parser = evolve_sub.add_parser(
        "proposals",
        help="List all evolution proposals.",
    )
    proposals_parser.add_argument(
        "--root",
        default=".",
        help="Project root (default: current directory).",
    )
    proposals_parser.add_argument(
        "--status",
        default=None,
        help="Filter by status (proposed, approved, rejected, applied).",
    )
    proposals_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )

    # approve
    approve_parser = evolve_sub.add_parser(
        "approve",
        help="Approve an evolution proposal by ID.",
    )
    approve_parser.add_argument("proposal_id", help="Proposal ID to approve.")
    approve_parser.add_argument("--root", default=".", help="Project root.")
    approve_parser.add_argument("--json", action="store_true", help="Output as JSON.")

    # reject
    reject_parser = evolve_sub.add_parser(
        "reject",
        help="Reject an evolution proposal by ID.",
    )
    reject_parser.add_argument("proposal_id", help="Proposal ID to reject.")
    reject_parser.add_argument("--root", default=".", help="Project root.")
    reject_parser.add_argument("--json", action="store_true", help="Output as JSON.")

    # apply
    apply_parser = evolve_sub.add_parser(
        "apply",
        help="Apply an approved evolution proposal by ID.",
    )
    apply_parser.add_argument("proposal_id", help="Proposal ID to apply.")
    apply_parser.add_argument("--root", default=".", help="Project root.")
    apply_parser.add_argument("--json", action="store_true", help="Output as JSON.")


def handle_evolve(args: argparse.Namespace) -> None:
    """Dispatch evolve subcommands."""
    cmd = getattr(args, "evolve_command", None)
    if cmd == "proposals":
        _handle_proposals(args)
    elif cmd == "approve":
        _handle_approve(args)
    elif cmd == "reject":
        _handle_reject(args)
    elif cmd == "apply":
        sys.exit(_handle_apply(args))
    else:
        eprint("evolve: unknown subcommand. Use --help for usage.")
        sys.exit(2)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _get_store(args: argparse.Namespace) -> EvolutionStore:
    """Return an EvolutionStore for the project root."""
    from opencontext_core.learning.evolution_store import EvolutionStore

    root = Path(getattr(args, "root", ".")).resolve()
    return EvolutionStore(root)


def _handle_proposals(args: argparse.Namespace) -> None:
    import json as _json

    store = _get_store(args)
    status_filter = getattr(args, "status", None)
    if status_filter:
        proposals = store.list_by_status(status_filter)
    else:
        proposals = store.list()

    as_json = getattr(args, "json", False)
    if as_json:
        print(_json.dumps([p.model_dump(mode="json") for p in proposals], indent=2))
        return

    console.header("Evolution Proposals")
    if not proposals:
        console.info("No evolution proposals yet.")
        return

    rows = [
        [
            p.proposal_id,
            str(p.kind),
            str(p.status),
            p.title if len(p.title) <= 60 else p.title[:57] + "...",
        ]
        for p in proposals
    ]
    console.table("Proposals", ["ID", "Kind", "Status", "Title"], rows)


def _handle_approve(args: argparse.Namespace) -> None:
    import json as _json

    store = _get_store(args)
    proposal_id = args.proposal_id
    updated = store.update_status(proposal_id, "approved")
    if updated is None:
        if getattr(args, "json", False):
            print(_json.dumps({"id": proposal_id, "status": "not_found"}))
        else:
            eprint(f"evolve approve: proposal '{proposal_id}' not found.")
        raise SystemExit(1)
    if getattr(args, "json", False):
        print(_json.dumps({"id": proposal_id, "status": "approved"}))
        return
    console.success(f"Proposal {proposal_id} approved.")


def _handle_reject(args: argparse.Namespace) -> None:
    import json as _json

    store = _get_store(args)
    proposal_id = args.proposal_id
    updated = store.update_status(proposal_id, "rejected")
    if updated is None:
        if getattr(args, "json", False):
            print(_json.dumps({"id": proposal_id, "status": "not_found"}))
        else:
            eprint(f"evolve reject: proposal '{proposal_id}' not found.")
        raise SystemExit(1)
    if getattr(args, "json", False):
        print(_json.dumps({"id": proposal_id, "status": "rejected"}))
        return
    console.warning(f"Proposal {proposal_id} rejected.")


def _handle_apply(args: argparse.Namespace) -> int:
    import json as _json

    from opencontext_core.learning.evolution_apply import EvolutionApplier

    store = _get_store(args)
    proposal_id = args.proposal_id
    proposal = store.load(proposal_id)

    if proposal is None:
        if getattr(args, "json", False):
            print(_json.dumps({"id": proposal_id, "status": "not_found"}))
        else:
            eprint(f"Evolution proposal not found: {proposal_id}")
        return 1

    if proposal.status != "approved":
        if getattr(args, "json", False):
            print(_json.dumps({"id": proposal_id, "status": "not_approved"}))
        else:
            eprint(
                f"Proposal {proposal_id} is not approved. "
                f"Run: opencontext evolve approve {proposal_id}"
            )
        return 1

    root = Path(getattr(args, "root", ".")).resolve()
    applier = EvolutionApplier(project_root=root)
    result = applier.apply(proposal, approved=True)

    if getattr(args, "json", False):
        status = "applied" if result.applied else "not_applied"
        print(_json.dumps({"id": proposal_id, "status": status}))
        return 0 if result.applied else 1

    if result.applied:
        console.success(f"Applied: {proposal.proposal_id}")
        for f in result.changed_files:
            console.dim(f"  modified: {f}")
        return 0
    else:
        eprint(f"Not applied: {result.reason}")
        return 1
