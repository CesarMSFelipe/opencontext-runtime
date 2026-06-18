"""Update CLI — check and apply OpenContext updates.

Usage:
  opencontext update           # Check for updates
  opencontext update --force   # Skip cache
  opencontext upgrade          # Check + install
"""

from __future__ import annotations

import sys
from typing import Any

from opencontext_core.update import EcosystemUpdateChecker, UpdateCheck, UpdateChecker


def _format_release_notes(check: UpdateCheck) -> str:
    if check.release_notes:
        return f"  Release notes: {check.release_notes}"
    return ""


def add_update_parser(subparsers: Any) -> None:
    """Add update command subparser."""

    update_parser = subparsers.add_parser(
        "update",
        help="Check for OpenContext updates.",
        description=(
            "Check the PyPI registry for newer versions of OpenContext.\n"
            "Results are cached for 24 hours."
        ),
    )
    update_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip cache and fetch from PyPI.",
    )


def add_upgrade_parser(subparsers: Any) -> None:
    """Add upgrade command subparser."""

    subparsers.add_parser(
        "upgrade",
        help="Upgrade OpenContext to the latest version.",
        description=(
            "Check for updates and install the latest version\nvia pip install --upgrade."
        ),
    )


def handle_update(args: Any) -> None:
    """Check for updates and display result."""

    check = UpdateChecker.check(force=getattr(args, "force", False))

    if check.is_outdated:
        print()
        print(f"  Update available: {check.current_version} -> {check.latest_version}")
        print(_format_release_notes(check))
        print()
        print("  Run 'opencontext upgrade' to install the latest version.")
        sys.exit(0)
    else:
        print(f"  ✓ OpenContext {check.current_version} is up to date.")
        if check.release_notes:
            print(_format_release_notes(check))
        sys.exit(0)


def handle_upgrade(args: Any) -> None:
    """Check and upgrade all OpenContext packages."""

    print()
    print("  Checking for OpenContext updates...")
    print()

    results = UpdateChecker.upgrade_all()

    upgraded = [r for r in results if r["status"] == "upgraded"]
    failed = [r for r in results if r["status"] == "failed"]

    print(f"  {'Package':<25} {'Status':<12} {'Message'}")
    print(f"  {'─' * 25} {'─' * 12} {'─' * 40}")
    for r in results:
        icon = "✓" if r["status"] == "upgraded" else "✗"
        print(f"  {r['package']:<25} {icon + ' ' + r['status']:<12} {r['message']}")
    print()

    if upgraded:
        print(f"  ✓ {len(upgraded)} package(s) upgraded.")
    if failed:
        print(f"  ✗ {len(failed)} package(s) failed.")
        sys.exit(1)
    if not upgraded and not failed:
        print("  ✓ All packages are up to date.")

    try:
        eco = EcosystemUpdateChecker.refresh()
        outdated_eco = [e for e in eco if e.is_outdated]
        if outdated_eco:
            print()
            print("  Ecosystem updates available:")
            for e in outdated_eco:
                print(f"    {e.name}: {e.current_version} -> {e.latest_version}")
            print("  Run 'pip install --upgrade <package>' to update.")
    except Exception:
        pass
