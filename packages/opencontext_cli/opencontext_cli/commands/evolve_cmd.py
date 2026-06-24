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
from pathlib import Path
from typing import Any


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

    # reject
    reject_parser = evolve_sub.add_parser(
        "reject",
        help="Reject an evolution proposal by ID.",
    )
    reject_parser.add_argument("proposal_id", help="Proposal ID to reject.")
    reject_parser.add_argument("--root", default=".", help="Project root.")


def handle_evolve(args: argparse.Namespace) -> None:
    """Dispatch evolve subcommands."""
    cmd = getattr(args, "evolve_command", None)
    if cmd == "proposals":
        _handle_proposals(args)
    elif cmd == "approve":
        _handle_approve(args)
    elif cmd == "reject":
        _handle_reject(args)
    else:
        print("evolve: unknown subcommand. Use --help for usage.")


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _get_store(args: argparse.Namespace):  # type: ignore[return]
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

    if not proposals:
        print("No evolution proposals found.")
        return

    # Table output
    col_id = 16
    col_kind = 22
    col_status = 10
    col_title = 40
    header = (
        f"{'ID':<{col_id}}  {'KIND':<{col_kind}}  {'STATUS':<{col_status}}  {'TITLE':<{col_title}}"
    )
    print(header)
    print("-" * len(header))
    for p in proposals:
        title = p.title if len(p.title) <= col_title else p.title[: col_title - 3] + "..."
        line = (
            f"{p.proposal_id:<{col_id}}  {p.kind:<{col_kind}}"
            f"  {p.status:<{col_status}}  {title:<{col_title}}"
        )
        print(line)


def _handle_approve(args: argparse.Namespace) -> None:
    store = _get_store(args)
    proposal_id = args.proposal_id
    updated = store.update_status(proposal_id, "approved")
    if updated is None:
        print(f"evolve approve: proposal '{proposal_id}' not found.")
        raise SystemExit(1)
    print(f"Proposal {proposal_id} approved.")


def _handle_reject(args: argparse.Namespace) -> None:
    store = _get_store(args)
    proposal_id = args.proposal_id
    updated = store.update_status(proposal_id, "rejected")
    if updated is None:
        print(f"evolve reject: proposal '{proposal_id}' not found.")
        raise SystemExit(1)
    print(f"Proposal {proposal_id} rejected.")
