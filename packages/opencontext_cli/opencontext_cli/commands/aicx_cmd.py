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
        print(f"Wrote {path}")
        return

    if action == "show":
        lock = build_lockfile(root)
        if getattr(args, "json", False):
            print(json.dumps(lock.model_dump(), indent=2))
        else:
            print(f"lock_hash: {lock.lock_hash}")
            for e in lock.entries:
                print(f"  {e.name}: {e.sha256[:16]}  ({e.detail})")
        return

    if action == "verify":
        result = verify_lockfile(root)
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2))
        elif result.get("ok"):
            print("OK  surface matches the pinned lock")
        else:
            err = result.get("error")
            if err == "not_locked":
                print("NOT LOCKED  run `opencontext aicx lock` first", file=sys.stderr)
            else:
                raw_drifted = result.get("drifted")
                drifted_list = raw_drifted if isinstance(raw_drifted, list) else []
                drifted = ", ".join(str(d) for d in drifted_list) or "?"
                print(f"DRIFT  surface changed: {drifted}", file=sys.stderr)
        sys.exit(0 if result.get("ok") else 1)

    print("Usage: opencontext aicx [lock|show|verify]")
    sys.exit(1)
