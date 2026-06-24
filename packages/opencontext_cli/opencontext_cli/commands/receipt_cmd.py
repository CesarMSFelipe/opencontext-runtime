"""receipt — inspect and verify run receipts.

Usage:
  opencontext receipt list [--json]
  opencontext receipt show <run_id> [--json]
  opencontext receipt verify <run_id>
  opencontext receipt export <run_id> --format markdown
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from opencontext_core.operating_model.receipts import RunReceiptStore


def _store(args: Any) -> RunReceiptStore:
    root = getattr(args, "root", None) or Path.cwd()
    return RunReceiptStore(root)


def add_receipt_parser(subparsers: Any) -> None:
    """Add receipt command group."""

    receipt_parser = subparsers.add_parser(
        "receipt",
        help="Inspect and verify run receipts.",
    )
    receipt_subs = receipt_parser.add_subparsers(dest="receipt_action")

    # list
    list_p = receipt_subs.add_parser("list", help="List stored run receipt IDs.")
    list_p.add_argument("--json", action="store_true", help="JSON output.")

    # show
    show_p = receipt_subs.add_parser("show", help="Show receipt details.")
    show_p.add_argument("run_id", help="Run ID.")
    show_p.add_argument("--json", action="store_true", help="JSON output.")

    # verify
    verify_p = receipt_subs.add_parser("verify", help="Verify receipt integrity.")
    verify_p.add_argument("run_id", help="Run ID.")

    # export
    export_p = receipt_subs.add_parser("export", help="Export receipt.")
    export_p.add_argument("run_id", help="Run ID.")
    export_p.add_argument("--format", default="markdown", choices=["markdown", "json"])


def handle_receipt(args: Any) -> None:
    """Dispatch receipt sub-command."""

    action = getattr(args, "receipt_action", None)

    if action == "list":
        store = _store(args)
        receipts = store.list()
        if args.json:
            print(json.dumps([r.run_id for r in receipts], indent=2))
        else:
            for r in receipts:
                print(r.run_id)

    elif action == "show":
        store = _store(args)
        try:
            receipt = store.load(args.run_id)
        except FileNotFoundError:
            print(f"Receipt not found: {args.run_id}", file=sys.stderr)
            sys.exit(1)
        data = json.loads(receipt.model_dump_json())
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(json.dumps(data, indent=2))

    elif action == "verify":
        store = _store(args)
        result = store.verify(args.run_id)
        if result.get("ok"):
            print(f"OK  {args.run_id}")
        else:
            print(f"INVALID  {args.run_id}  {result.get('error', '')}", file=sys.stderr)
            sys.exit(1)

    elif action == "export":
        store = _store(args)
        try:
            receipt = store.load(args.run_id)
        except FileNotFoundError:
            print(f"Receipt not found: {args.run_id}", file=sys.stderr)
            sys.exit(1)
        fmt = getattr(args, "format", "markdown")
        if fmt == "json":
            print(receipt.model_dump_json(indent=2))
        else:
            data = json.loads(receipt.model_dump_json())
            headers = list(data.keys())
            values = [str(v) for v in data.values()]
            print("| " + " | ".join(headers) + " |")
            print("| " + " | ".join("---" for _ in headers) + " |")
            print("| " + " | ".join(values) + " |")

    else:
        print("Usage: opencontext receipt [list|show|verify|export]")
        sys.exit(1)
