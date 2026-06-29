"""Verification CLI — run post-install health checks.

Usage:
  opencontext verify           # Run all checks
  opencontext verify --json    # JSON output (CI-friendly)
"""

from __future__ import annotations

import json
import sys
from typing import Any

from opencontext_core.verification import build_report_payload, run_all_checks


def add_verify_parser(subparsers: Any) -> None:
    """Add verify command subparser."""

    verify_parser = subparsers.add_parser(
        "verify",
        help="Run component health checks.",
        description=(
            "Verify that all OpenContext components are installed and working.\n"
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
        data = build_report_payload(report)
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.exit(0 if report.is_healthy else 1)

    # ── Branded report ──────────────────────────────────────────────────
    # Route through the canonical BrandConsole (logo + brand panel + heavy-box
    # brand table) and degrade to plain text automatically when rich is absent.
    from opencontext_core.dx.console_styles import (
        BRAND_ERROR,
        BRAND_SUCCESS,
        BRAND_WARNING,
        console,
    )

    STATUS_LABELS = {
        "passed": "✓ passed",
        "warning": "⚠ warning",
        "failed": "✗ failed",
        "skipped": "- skipped",
    }

    console.header("OpenContext Health Check")
    console.table(
        "Component Checks",
        ["Check", "Status", "Message"],
        [[r.name, STATUS_LABELS.get(r.status, r.status), r.message] for r in report.results],
    )

    parts = []
    if report.passed:
        parts.append(f"[{BRAND_SUCCESS}]{report.passed} passed[/]")
    if report.warnings:
        parts.append(f"[{BRAND_WARNING}]{report.warnings} warnings[/]")
    if report.failures:
        parts.append(f"[{BRAND_ERROR}]{report.failures} failed[/]")
    if parts:
        console.print("  ".join(parts))

    if report.is_healthy:
        console.success("All checks passed")
    else:
        console.error(
            f"{report.failures} check(s) failed — run 'opencontext doctor' for details"
        )
        # Honest exit code so CI can gate on `opencontext verify`.
        sys.exit(1)
