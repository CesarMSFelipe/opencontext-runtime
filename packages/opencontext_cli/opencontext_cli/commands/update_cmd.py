"""Update CLI — check and apply OpenContext updates.

Usage:
  opencontext update           # Check for updates
  opencontext update --force   # Skip cache
  opencontext upgrade          # Check + install
"""

from __future__ import annotations

import sys
from typing import Any

from opencontext_cli.output import eprint
from opencontext_core.dx.console_styles import console
from opencontext_core.update import EcosystemUpdateChecker, UpdateCheck, UpdateChecker


def _format_release_notes(check: UpdateCheck) -> str:
    if check.release_notes:
        return f"Release notes: {check.release_notes}"
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

    console.header("Check for Updates")
    if check.is_outdated:
        console.info(f"Update available: {check.current_version} -> {check.latest_version}")
        if check.release_notes:
            console.dim(_format_release_notes(check))
        console.print()
        console.info("Run 'opencontext upgrade' to install the latest version.")
        sys.exit(0)
    else:
        console.success(f"OpenContext {check.current_version} is up to date.")
        if check.release_notes:
            console.dim(_format_release_notes(check))
        sys.exit(0)


def handle_upgrade(args: Any) -> None:
    """Check and upgrade all OpenContext packages."""

    console.header("Upgrade OpenContext")
    console.info("Checking for OpenContext updates...")

    results = UpdateChecker.upgrade_all()

    upgraded = [r for r in results if r["status"] == "upgraded"]
    failed = [r for r in results if r["status"] == "failed"]

    console.table(
        "Upgrade Results",
        ["Package", "Status", "Message"],
        [
            [
                r["package"],
                ("✓ " if r["status"] == "upgraded" else "✗ ") + r["status"],
                r["message"],
            ]
            for r in results
        ],
    )

    if upgraded:
        console.success(f"{len(upgraded)} package(s) upgraded.")
    if failed:
        eprint(f"{len(failed)} package(s) failed.")
        sys.exit(1)
    if not upgraded and not failed:
        console.success("All packages are up to date.")

    try:
        eco = EcosystemUpdateChecker.refresh()
        outdated_eco = [e for e in eco if e.is_outdated]
        if outdated_eco:
            console.section("Ecosystem updates available")
            for e in outdated_eco:
                console.print(f"    {e.name}: {e.current_version} -> {e.latest_version}")
            console.dim("Run 'pip install --upgrade <package>' to update.")
    except Exception:
        pass
