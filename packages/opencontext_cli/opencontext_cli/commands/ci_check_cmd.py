"""CI check CLI commands."""

from __future__ import annotations

import json
from typing import Any

from opencontext_core.dx.console_styles import console
from opencontext_core.quality.ci_checks import CheckRunner


def add_ci_check_parser(subparsers: Any) -> None:
    """Add ci-check command parsers."""
    check_parser = subparsers.add_parser("ci-check", help="CI check management.")
    check_sub = check_parser.add_subparsers(dest="ci_check_command", required=True)
    check_sub.add_parser("init", help="Initialize checks directory.")
    check_sub.add_parser("list", help="List discovered checks.")
    check_run = check_sub.add_parser("run", help="Run all checks.")
    check_run.add_argument("--file", help="Run on specific file only.")
    check_run.add_argument("--json", action="store_true")
    check_create = check_sub.add_parser("create", help="Create a new check template.")
    check_create.add_argument("name", help="Check name.")
    check_create.add_argument("--description", default="", help="Check description.")


def handle_ci_check(args: Any) -> None:
    """Handle ci-check commands."""
    command = args.ci_check_command
    name = getattr(args, "name", None)
    file = getattr(args, "file", None)
    json_output = getattr(args, "json", False)

    runner = CheckRunner()

    if command == "init":
        path = runner.init_checks_directory()
        console.success(f"Initialized checks directory: {path}")
    elif command == "list":
        checks = runner.discover_checks()
        if json_output:
            data = [
                {"name": c.name, "description": c.description, "severity": c.severity.value}
                for c in checks
            ]
            print(json.dumps(data, indent=2))
        else:
            console.header("CI Checks")
            if not checks:
                console.dim(
                    "No checks found. Run 'opencontext ci-check init'"
                )
            else:
                console.table(
                    "Discovered Checks",
                    ["Name", "Severity", "Description"],
                    [[c.name, c.severity.value, c.description] for c in checks],
                )
    elif command == "run":
        files = [file] if file else None
        with console.progress("Running checks...") as progress:
            task = progress.add_task("Running checks...", total=None)
            results = runner.run_all_checks(files)
            progress.update(task, completed=True)
        report = runner.generate_report(results)
        if json_output:
            print(json.dumps(report, indent=2))
        else:
            _display_check_report(report)
    elif command == "create" and name:
        template = runner.create_check_template(name, "Custom check")
        console.print(template)
    else:
        console.error(f"Unknown ci-check command: {command}")


def _display_check_report(report: dict[str, Any]) -> None:
    """Display a formatted check report."""
    summary = report.get("summary", {})
    total = summary.get("total_checks", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    warnings = summary.get("warnings", 0)
    errors = summary.get("errors", 0)
    success = summary.get("success", False)

    console.header("Check Report")

    if success:
        console.success(f"All {total} checks passed")
    else:
        console.error(f"{failed}/{total} checks failed")

    console.table(
        "Summary",
        ["Metric", "Count"],
        [
            ["Total", str(total)],
            ["Passed", str(passed)],
            ["Failed", str(failed)],
            ["Warnings", str(warnings)],
            ["Errors", str(errors)],
        ],
    )

    # Show failed results
    failed_results = [r for r in report.get("results", []) if r["status"] != "passed"]
    if failed_results:
        console.section("Failed Checks")
        for r in failed_results:
            severity_color = "#FF6F91" if r["severity"] in ("error", "critical") else "#FFC75F"
            msg = f"  [bold {severity_color}]{r['severity'].upper()}[/]"
            msg += f" {r['check']}: {r['message']}"
            console.print(msg)
            if r.get("file"):
                console.print(f"    [dim]File: {r['file']}:{r.get('line', 'N/A')}[/]")
            if r.get("suggestion"):
                console.print(f"    [dim]Suggestion: {r['suggestion']}[/]")
