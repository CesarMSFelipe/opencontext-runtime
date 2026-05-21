"""Verification CLI — run post-install health checks.

Usage:
  opencontext verify           # Run all checks
  opencontext verify --json    # JSON output (CI-friendly)
"""

from __future__ import annotations

import json
import sys
from typing import Any

from opencontext_core.verification import run_all_checks


def add_verify_parser(subparsers: Any) -> None:
    """Add verify command subparser."""

    verify_parser = subparsers.add_parser(
        "verify",
        help="Run post-install health checks.",
        description=(
            "Verify that OpenContext components are installed and working.\n"
            "Runs checks for Python version, user config, tree-sitter,\n"
            "knowledge graph, MCP config, plugins, and more."
        ),
    )
    verify_parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (CI-friendly).",
    )


def handle_verify(args: Any) -> None:
    """Run verification and display results."""

    report = run_all_checks()

    if args.json:
        data = {
            "timestamp": report.timestamp,
            "healthy": report.is_healthy,
            "summary": {
                "passed": report.passed,
                "warnings": report.warnings,
                "failures": report.failures,
            },
            "checks": [
                {
                    "name": r.name,
                    "status": r.status,
                    "message": r.message,
                    "details": r.details,
                }
                for r in report.results
            ],
        }
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.exit(0 if report.is_healthy else 1)

    # ── Rich table output ──────────────────────────────────────────────
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.text import Text

        console = Console()

        table = Table(title="OpenContext Health Check", show_lines=True)
        table.add_column("Check", style="bold")
        table.add_column("Status", width=10)
        table.add_column("Message")

        STATUS_STYLES = {
            "passed": "✓ passed",
            "warning": "⚠ warning",
            "failed": "✗ failed",
            "skipped": "-- skipped",
        }

        for r in report.results:
            status_text = Text(STATUS_STYLES.get(r.status, r.status))
            table.add_row(r.name, status_text, r.message)

        console.print()
        console.print(table)
        console.print()

        # Summary line
        parts = []
        if report.passed:
            parts.append(f"[green]{report.passed} passed[/green]")
        if report.warnings:
            parts.append(f"[yellow]{report.warnings} warnings[/yellow]")
        if report.failures:
            parts.append(f"[red]{report.failures} failed[/red]")
        console.print("  ".join(parts))

        if report.is_healthy:
            console.print("\n[bold green]✓ All checks passed[/bold green]")
        else:
            console.print(
                f"\n[bold red]✗ {report.failures} check(s) failed — "
                "run 'opencontext doctor' for details[/bold red]"
            )

    except ImportError:
        # Fallback: plain text
        print(f"\nOpenContext Health Check ({report.timestamp})")
        print("=" * 50)
        for r in report.results:
            icon = {"passed": "✓", "warning": "⚠", "failed": "✗", "skipped": "--"}.get(
                r.status, "?"
            )
            print(f"  {icon} {r.name}: {r.message}")
        print(f"\n{report.passed} passed, {report.warnings} warnings, {report.failures} failed")

        if not report.is_healthy:
            sys.exit(1)
