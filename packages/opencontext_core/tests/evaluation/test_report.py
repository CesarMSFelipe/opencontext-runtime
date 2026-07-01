"""REQ-eval-fw-002/003: EvalReport + generate_report() factory + regression list."""

from __future__ import annotations

from opencontext_core.evaluation.report import (
    EvalCaseResult,
    EvalRegression,
    EvalReport,
    generate_report,
)
from opencontext_core.evaluation.runner import EvalSuite, run_suite

# ── EvalCaseResult / EvalRegression / EvalReport dataclasses ────────────────


def test_eval_case_result_defaults() -> None:
    r = EvalCaseResult(case_id="c1", passed=True, score=1.0)
    assert r.case_id == "c1"
    assert r.passed is True
    assert r.score == 1.0
    assert r.duration_ms == 0
    assert r.reasons == []


def test_eval_regression_carries_axis() -> None:
    reg = EvalRegression(
        case_id="lockout",
        before=1.0,
        after=0.5,
        delta=-0.5,
        axis="score",
    )
    assert reg.case_id == "lockout"
    assert reg.delta == -0.5
    assert reg.axis == "score"


def test_eval_report_passes_when_all_pass() -> None:
    results = [EvalCaseResult(case_id="c1", passed=True, score=1.0)]
    report = generate_report(
        suite="first_run",
        methodology_version="2026.07.01",
        results=results,
        microseconds_total=1234,
    )
    assert report.verdict == "pass"
    assert report.passed is True
    assert report.failed is False
    assert report.microseconds_total == 1234
    assert report.regressions == []


def test_eval_report_fails_when_any_case_fails() -> None:
    results = [
        EvalCaseResult(case_id="c1", passed=True, score=1.0),
        EvalCaseResult(case_id="c2", passed=False, score=0.0, reasons=["boom"]),
    ]
    report = generate_report(
        suite="security",
        methodology_version="2026.07.01",
        results=results,
    )
    assert report.verdict == "fail"
    assert report.passed is False
    assert report.failed is True


def test_eval_report_regressions_drive_verdict_to_regression() -> None:
    # All cases pass BUT a regression was detected → verdict must be "regression"
    # (the spec rule: "regression in any gate block release").
    results = [EvalCaseResult(case_id="c1", passed=True, score=1.0)]
    regressions = [
        EvalRegression(
            case_id="c1",
            before=1.0,
            after=0.8,
            delta=-0.2,
            axis="score",
        ),
    ]
    report = generate_report(
        suite="regression",
        methodology_version="2026.07.01",
        results=results,
        regressions=regressions,
    )
    assert report.verdict == "regression"
    assert len(report.regressions) == 1
    assert report.regressions[0].case_id == "c1"


# ── generate_report() / run_suite() integration ─────────────────────────────


def test_generate_report_runs_via_suite() -> None:
    """End-to-end: a real suite flows through run_suite() and back via generate_report()."""
    suite = EvalSuite(
        name="feature",
        methodology_version="2026.07.01",
        cases=[
            {"id": "add-feature-1", "run": lambda: {"passed": True, "score": 1.0}},
            {"id": "add-feature-2", "run": lambda: {"passed": False, "score": 0.0}},
        ],
    )
    report = run_suite(suite)
    # run_suite calls generate_report under the hood.
    assert isinstance(report, EvalReport)
    assert report.suite == "feature"
    assert report.verdict == "fail"
    assert len(report.results) == 2
    assert report.results[0].case_id == "add-feature-1"
    assert report.results[1].case_id == "add-feature-2"


def test_generate_report_microseconds_is_non_negative_int() -> None:
    report = generate_report(
        suite="x",
        methodology_version="2026.07.01",
        results=[],
        microseconds_total=0,
    )
    assert isinstance(report.microseconds_total, int)
    assert report.microseconds_total == 0
