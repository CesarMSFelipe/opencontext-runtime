"""aicx — pin and verify the agentic context surface (Workstream N).

Usage:
  opencontext aicx lock            Write .opencontext/aicx.lock
  opencontext aicx show [--json]   Show the current (computed) surface
  opencontext aicx verify          Compare the pinned lock against current
"""

from __future__ import annotations

import json
import sys
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console
from opencontext_core.models.aicx_lock import (
    build_lockfile,
    verify_lockfile,
    write_lockfile,
)


def add_aicx_parser(subparsers: Any) -> None:
    aicx_parser = subparsers.add_parser(
        "aicx", help="Pin/verify the agentic context surface (schemas, clients, graph)."
    )
    aicx_subs = aicx_parser.add_subparsers(dest="aicx_action")

    lock_p = aicx_subs.add_parser("lock", help="Write the lockfile.")
    lock_p.add_argument("--root", default=".", help="Project root.")

    show_p = aicx_subs.add_parser("show", help="Show the current surface (without writing).")
    show_p.add_argument("--root", default=".", help="Project root.")
    show_p.add_argument("--json", action="store_true", help="JSON output.")

    verify_p = aicx_subs.add_parser("verify", help="Compare the pinned lock against current.")
    verify_p.add_argument("--root", default=".", help="Project root.")
    verify_p.add_argument("--json", action="store_true", help="JSON output.")


def handle_aicx(args: Any) -> None:
    action = getattr(args, "aicx_action", None)
    root = getattr(args, "root", ".")

    if action == "lock":
        path = write_lockfile(root)
        console.success(f"Wrote {path}")
        return

    if action == "show":
        lock = build_lockfile(root)
        if getattr(args, "json", False):
            print(json.dumps(lock.model_dump(), indent=2))
            return
        console.header("AICX Surface")
        console.print(f"  lock_hash: {lock.lock_hash}")
        if not lock.entries:
            console.info("No surface entries yet.")
            return
        rows = [[e.name, e.sha256[:16], str(e.detail)] for e in lock.entries]
        console.table("Entries", ["Name", "SHA-256", "Detail"], rows)
        return

    if action == "verify":
        result = verify_lockfile(root)
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            console.success("Surface matches the pinned lock")
        else:
            err = result.get("error")
            if err == "not_locked":
                eprint("Not locked — run `opencontext aicx lock` first")
            else:
                raw_drifted = result.get("drifted")
                drifted_list = raw_drifted if isinstance(raw_drifted, list) else []
                drifted = ", ".join(str(d) for d in drifted_list) or "?"
                eprint(f"Drift — surface changed: {drifted}")
        sys.exit(0 if result.get("ok") else 1)

    eprint("Usage: opencontext aicx [lock|show|verify]")
    sys.exit(1)
