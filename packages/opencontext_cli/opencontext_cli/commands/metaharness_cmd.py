"""MetaHarness CLI command — ``opencontext doctor metaharness``.

Runs the pre-flight MetaHarnessScanner and prints a scored capability report.
Exit code 0 when score >= 90 (passed), exit code 1 otherwise.
"""

from __future__ import annotations

from typing import Any


def add_metaharness_parser(doctor_sub: Any) -> None:
    """Register ``metaharness`` subcommand under the ``doctor`` subparser group."""
    parser = doctor_sub.add_parser(
        "metaharness",
        help="Pre-flight capability readiness scanner (scores 0-100).",
        description=(
            "Runs 9 independent readiness checks and scores the installation 0-100.\n"
            "Exit code 0 when score >= 90, exit code 1 otherwise.\n\n"
            "  opencontext doctor metaharness\n"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON.",
    )


def handle_doctor_metaharness(args: Any) -> None:
    """Handle ``opencontext doctor metaharness`` invocation."""
    import json as _json

    from opencontext_core.harness.meta import MetaHarnessScanner

    scanner = MetaHarnessScanner()
    report = scanner.scan()

    json_output = getattr(args, "json_output", False)

    if json_output:
        output = {
            "score": report.score,
            "passed": report.passed,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "score_contribution": c.score_contribution,
                    "explanation": c.explanation,
                }
                for c in report.checks
            ],
        }
        print(_json.dumps(output, indent=2))
    else:
        status_icon = "PASS" if report.passed else "FAIL"
        print(f"MetaHarness readiness scan [{status_icon}]  score={report.score}/100")
        print()
        for check in report.checks:
            icon = "OK" if check.passed else "FAIL"
            expl = check.explanation
            print(f"  [{icon:4s}] {check.name:30s}  +{check.score_contribution:2d}  {expl}")
        print()
        if report.passed:
            print(f"All checks passed - score {report.score}/100.")
        else:
            failed = [c for c in report.checks if not c.passed]
            print(f"{len(failed)} check(s) failed - score {report.score}/100 (gate: >=90).")

    if not report.passed:
        raise SystemExit(1)
