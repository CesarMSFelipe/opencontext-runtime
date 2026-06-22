"""``opencontext quality check`` / ``quality gate`` — the architecture & code-quality CLI.

This module wires the deterministic :class:`~opencontext_core.quality.evaluator.QualityEvaluator`
to the CLI. It attaches two subcommands onto the EXISTING ``quality`` argparse group
(which already owns the unrelated CONTEXT-quality ``preflight``/``verify`` gates):

* ``check [--json] [--diff] [path]`` — evaluate architecture + language quality on the
  changed scope (``--diff``) or the whole project, print a report, and exit 0 when clean
  / 1 on a violation.
* ``gate --save`` — capture the ratchet baseline (findings + metrics + score) so later
  ``check`` runs only block on NEW violations.

The check path is deterministic and makes ZERO model calls — it reads the persisted
knowledge graph and (for the language tier) runs lint/type tools as subprocesses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opencontext_core.dx.console_styles import console

# Import the evaluator from its submodule (not the package re-export) so this command
# does not depend on the optional ``quality/__init__.py`` aggregate surface.
from opencontext_core.quality.evaluator import QualityEvaluator


def add_quality_subcommands(quality_sub: Any) -> None:
    """Attach ``check`` and ``gate`` to the EXISTING ``quality`` subparser group.

    A second top-level ``quality`` parser cannot be registered (argparse name
    collision with the legacy context-quality group), so the caller passes in the
    already-created ``quality_sub`` and we add onto it.
    """
    check_parser = quality_sub.add_parser(
        "check",
        help="Evaluate architecture + code quality (deterministic, zero model calls).",
    )
    check_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root to evaluate (default: current directory).",
    )
    check_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the machine-readable report instead of a console table.",
    )
    check_parser.add_argument(
        "--diff",
        action="store_true",
        help="Scope the evaluation to git working-tree changes only.",
    )

    gate_parser = quality_sub.add_parser(
        "gate",
        help="Manage the ratchet baseline used by `quality check`.",
    )
    gate_parser.add_argument(
        "--save",
        action="store_true",
        help="Capture the current findings/metrics/score as the ratchet baseline.",
    )


def _changed_files(root: Path) -> list[str]:
    """Working-tree changes for ``--diff`` scope (reuses the harness helper).

    Falls back to an empty list (whole-graph metrics still run; no files are
    scoped) when git is unavailable, so the command never crashes on the scope
    derivation.
    """
    try:
        from opencontext_core.harness.runner import HarnessRunner

        return HarnessRunner._git_changed_files(root)
    except Exception:
        return []


def handle_quality_check(args: Any) -> None:
    """Run the full quality evaluation and exit 0 (clean) / 1 (violation).

    ``--diff`` scopes findings to git-changed files; otherwise the whole repo is
    evaluated. ``--json`` prints the ``to_report_dict`` shape (the same schema as
    ``ci-check run``); the default is a console table.
    """
    root = Path(getattr(args, "path", ".") or ".").resolve()
    json_output = bool(getattr(args, "json", False))
    diff_only = bool(getattr(args, "diff", False))

    evaluator = QualityEvaluator(root)
    changed = _changed_files(root) if diff_only else []
    report = evaluator.evaluate(changed)
    report_dict = report.to_report_dict()

    if json_output:
        print(json.dumps(report_dict, indent=2))
    else:
        _display_quality_report(report_dict, report.summary, report.skipped)

    raise SystemExit(report.exit_code)


def handle_quality_gate(args: Any) -> None:
    """Capture the ratchet baseline (``quality gate --save``) and exit 0.

    Without ``--save`` the subcommand is a no-op that simply explains what it
    would do, so an accidental bare ``quality gate`` never silently overwrites a
    baseline.
    """
    root = Path(getattr(args, "path", ".") or ".").resolve()

    if not getattr(args, "save", False):
        console.warning(
            "Nothing to do. Use `opencontext quality gate --save` to capture a baseline."
        )
        raise SystemExit(0)

    evaluator = QualityEvaluator(root)
    baseline = evaluator.save_baseline()
    baseline_path = root / evaluator.rules.baseline_path
    console.success(f"Saved quality baseline: {baseline_path}")
    console.dim(f"  score={baseline.score} findings={len(baseline.keys)}")
    raise SystemExit(0)


def _display_quality_report(
    report: dict[str, Any],
    summary_line: str,
    skipped: tuple[str, ...],
) -> None:
    """Render the quality report as a console table (ci-check style)."""
    summary = report.get("summary", {})
    total = int(summary.get("total_checks", 0))
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    warnings = int(summary.get("warnings", 0))
    errors = int(summary.get("errors", 0))
    success = bool(summary.get("success", False))
    health = report.get("health", {})

    console.header("Quality Report")

    if success:
        console.success(summary_line or "Quality check passed")
    else:
        console.error(summary_line or f"{failed}/{total} quality checks failed")

    console.table(
        "Summary",
        ["Metric", "Count"],
        [
            ["Health", str(health.get("score", "N/A"))],
            ["Delta", str(report.get("delta", 0))],
            ["Total", str(total)],
            ["Passed", str(passed)],
            ["Failed", str(failed)],
            ["Warnings", str(warnings)],
            ["Errors", str(errors)],
        ],
    )

    findings = [r for r in report.get("results", []) if r.get("status") != "passed"]
    if findings:
        console.section("Findings")
        for r in findings:
            severity = str(r.get("severity", "warning"))
            severity_color = "#FF6F91" if severity in ("error", "critical") else "#FFC75F"
            msg = f"  [bold {severity_color}]{severity.upper()}[/]"
            msg += f" {r.get('check', '?')}: {r.get('message', '')}"
            console.print(msg)
            if r.get("file"):
                console.print(f"    [dim]File: {r['file']}:{r.get('line', 'N/A')}[/]")
            if r.get("suggestion"):
                console.print(f"    [dim]Suggestion: {r['suggestion']}[/]")

    if skipped:
        console.section("Skipped")
        for reason in skipped:
            console.dim(f"  {reason}")
