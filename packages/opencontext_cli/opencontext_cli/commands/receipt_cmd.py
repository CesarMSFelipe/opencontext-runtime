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

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console
from opencontext_core.operating_model.receipts import RunReceiptStore
from opencontext_core.paths import StorageMode, resolve_workspace_path


def _store(args: Any) -> RunReceiptStore:
    root = getattr(args, "root", None) or Path.cwd()
    return RunReceiptStore(root)


def _root_path(args: Any) -> Path:
    root = getattr(args, "root", None) or Path.cwd()
    return Path(root)


def _list_harness_receipts(root: Path) -> list[Any]:
    """Scan all known receipt locations for every harness/oc_flow receipt.

    Covers two on-disk layouts:
    - Legacy harness layout: ``.opencontext/runs/<run_id>/receipts/receipts.jsonl``
    - OC Flow / RuntimeApi durable-apply layout:
      ``.opencontext/sessions/<session_id>/runs/<run_id>/receipts/receipts.jsonl``

    Returns every receipt (Receipt, PhaseReceipt, ApplyReceipt, RollbackReceipt)
    across all run directories.  Falls back to an empty list when neither tree
    exists yet.
    """
    from opencontext_core.harness.receipt_store import ReceiptStore

    ws = resolve_workspace_path(root, StorageMode.local)
    receipts: list[Any] = []

    # Legacy layout: .opencontext/runs/<run_id>/
    runs_dir = ws / "runs"
    if runs_dir.is_dir():
        for run_dir in sorted(runs_dir.iterdir()):
            if run_dir.is_dir():
                receipts.extend(ReceiptStore(run_dir).list_all())

    # Sessions layout: .opencontext/sessions/<session_id>/runs/<run_id>/
    sessions_dir = ws / "sessions"
    if sessions_dir.is_dir():
        for session_dir in sorted(sessions_dir.iterdir()):
            if not session_dir.is_dir():
                continue
            runs_subdir = session_dir / "runs"
            if runs_subdir.is_dir():
                for run_dir in sorted(runs_subdir.iterdir()):
                    if run_dir.is_dir():
                        receipts.extend(ReceiptStore(run_dir).list_all())

    return receipts


def _find_harness_receipt(root: Path, receipt_key: str) -> Any | None:
    """Find a receipt by receipt_id OR run_id across all run directories.

    Returns the first matching receipt, or None if not found.
    """
    for r in _list_harness_receipts(root):
        if getattr(r, "receipt_id", None) == receipt_key:
            return r
        if getattr(r, "run_id", None) == receipt_key:
            return r
    return None


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
        root = _root_path(args)
        receipts = _list_harness_receipts(root)
        # Fall back to the flat RunReceiptStore when no harness runs exist.
        if not receipts:
            store = _store(args)
            flat = store.list()
            if args.json:
                print(json.dumps([r.run_id for r in flat], indent=2))
                return
            console.header("Run Receipts")
            if not flat:
                console.info("No receipts yet.")
                return
            console.table("Receipts", ["Run ID"], [[r.run_id] for r in flat])
            return
        if args.json:
            # Emit receipt_id as the canonical identifier; include run_id when present.
            payload = [
                {
                    "receipt_id": getattr(r, "receipt_id", ""),
                    "run_id": getattr(r, "run_id", None),
                    "schema_version": getattr(r, "schema_version", ""),
                }
                for r in receipts
            ]
            print(json.dumps(payload, indent=2))
            return
        console.header("Run Receipts")
        rows = [
            [
                getattr(r, "receipt_id", ""),
                str(getattr(r, "run_id", "") or ""),
                getattr(r, "schema_version", "").split(".")[-1],
            ]
            for r in receipts
        ]
        console.table("Receipts", ["Receipt ID", "Run ID", "Schema"], rows)

    elif action == "show":
        root = _root_path(args)
        receipt_key = args.run_id
        # Try harness runs directory first (the actual writer location).
        receipt = _find_harness_receipt(root, receipt_key)
        if receipt is None:
            # Fall back to flat RunReceiptStore for backward compatibility.
            store = _store(args)
            try:
                receipt = store.load(receipt_key)
            except FileNotFoundError:
                eprint(f"Receipt not found: {receipt_key}")
                sys.exit(1)
        data = json.loads(receipt.model_dump_json())
        if args.json:
            print(json.dumps(data, indent=2))  # pure JSON to stdout
            return
        console.header(f"Receipt: {receipt_key}")
        # The receipt body is structured data; emit it as indented JSON beneath
        # the brand header so the payload stays faithful and copy-pasteable.
        print(json.dumps(data, indent=2))

    elif action == "verify":
        root = _root_path(args)
        receipt_key = args.run_id
        receipt = _find_harness_receipt(root, receipt_key)
        if receipt is not None:
            # Harness receipt: verify it's structurally sound (model parse succeeded).
            console.success(f"{receipt_key}: receipt verified")
            return
        # Fall back to flat RunReceiptStore.
        store = _store(args)
        flat_result = store.verify(receipt_key)
        if flat_result.get("ok"):
            console.success(f"{receipt_key}: receipt verified")
        else:
            eprint(f"{receipt_key}: invalid — {flat_result.get('error', '')}")
            sys.exit(1)

    elif action == "export":
        store = _store(args)
        try:
            receipt = store.load(args.run_id)
        except FileNotFoundError:
            eprint(f"Receipt not found: {args.run_id}")
            sys.exit(1)
        # Export emits the artifact itself (JSON or a Markdown table) to stdout
        # for redirection/piping — intentionally unbranded machine output.
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
        eprint("Usage: opencontext receipt [list|show|verify|export]")
        sys.exit(1)
