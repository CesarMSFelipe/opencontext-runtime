"""REQ-eval-fw-001/002: EvalSuite + EvalRunner + run_suite() harness.

NOTE: file is named ``test_eval_runner.py`` (not ``test_runner.py``) to avoid
a basename collision with ``tests/benchmarks/v2/test_runner.py`` under
pytest's default collection — both would resolve to module ``test_runner``.
"""

from __future__ import annotations

import pytest

from opencontext_core.evaluation.report import EvalReport
from opencontext_core.evaluation.runner import EvalRunner, EvalSuite, run_suite


def _noop_case(case_id: str, passed: bool = True, score: float = 1.0) -> dict:
    """A trivial in-memory case payload; the runner's case-callable drives it."""

    def _run() -> dict:
        return {"case_id": case_id, "passed": passed, "score": score}

    return _run


# ── EvalSuite dataclass ──────────────────────────────────────────────────────


def test_eval_suite_defaults_match_spec() -> None:
    suite = EvalSuite(name="regression", methodology_version="2026.07.01")
    # Per spec §C.3 REQ-eval-fw-001: gate_blocking defaults True,
    # regression_threshold is configurable (sensible default).
    assert suite.gate_blocking is True
    assert suite.cases == []
    assert suite.regression_threshold == pytest.approx(0.05)
    assert suite.methodology_version == "2026.07.01"


def test_eval_suite_carries_cases() -> None:
    suite = EvalSuite(
        name="first_run",
        methodology_version="2026.07.01",
        cases=[{"id": "init"}, {"id": "doctor"}],
    )
    assert len(suite.cases) == 2


# ── EvalRunner.register / list_suites / get_suite ───────────────────────────


def test_eval_runner_register_and_list() -> None:
    runner = EvalRunner()
    runner.register(EvalSuite(name="first_run", methodology_version="2026.07.01"))
    runner.register(EvalSuite(name="regression", methodology_version="2026.07.01"))
    assert sorted(runner.list_suites()) == ["first_run", "regression"]


def test_eval_runner_register_rejects_duplicate() -> None:
    runner = EvalRunner()
    runner.register(EvalSuite(name="x", methodology_version="2026.07.01"))
    with pytest.raises(ValueError):
        runner.register(EvalSuite(name="x", methodology_version="2026.07.01"))


def test_eval_runner_register_replace_overwrites() -> None:
    runner = EvalRunner()
    runner.register(EvalSuite(name="x", methodology_version="2026.07.01"))
    runner.register(EvalSuite(name="x", methodology_version="2026.08.01"), replace=True)
    assert runner.get_suite("x").methodology_version == "2026.08.01"


def test_eval_runner_unknown_suite_raises() -> None:
    runner = EvalRunner()
    with pytest.raises(KeyError):
        runner.get_suite("nope")


# ── EvalRunner.run ───────────────────────────────────────────────────────────


def test_eval_runner_run_all_passing_returns_pass() -> None:
    suite = EvalSuite(
        name="first_run",
        methodology_version="2026.07.01",
        cases=[{"id": "init", "run": _noop_case("init", passed=True, score=1.0)}],
    )
    runner = EvalRunner()
    runner.register(suite)
    report = runner.run("first_run")
    assert isinstance(report, EvalReport)
    assert report.suite == "first_run"
    assert report.methodology_version == "2026.07.01"
    assert report.verdict == "pass"
    assert all(r.passed for r in report.results)
    assert report.microseconds_total >= 0


def test_eval_runner_run_failing_returns_fail() -> None:
    suite = EvalSuite(
        name="security",
        methodology_version="2026.07.01",
        cases=[{"id": "secret-leak", "run": _noop_case("secret-leak", passed=False, score=0.0)}],
    )
    runner = EvalRunner()
    runner.register(suite)
    report = runner.run("security")
    assert report.verdict == "fail"
    assert any(not r.passed for r in report.results)


def test_eval_runner_run_unknown_raises() -> None:
    runner = EvalRunner()
    with pytest.raises(KeyError):
        runner.run("does-not-exist")


def test_eval_runner_run_empty_suite_yields_empty_results() -> None:
    # An empty suite is a degenerate pass (nothing to fail).
    runner = EvalRunner()
    runner.register(EvalSuite(name="empty", methodology_version="2026.07.01"))
    report = runner.run("empty")
    assert report.results == []
    assert report.verdict == "pass"
    assert report.regressions == []


# ── run_suite() free function ────────────────────────────────────────────────


def test_run_suite_function_matches_runner_run() -> None:
    suite = EvalSuite(
        name="bug_fix",
        methodology_version="2026.07.01",
        cases=[{"id": "lockout", "run": _noop_case("lockout", passed=True)}],
    )
    report = run_suite(suite)
    assert report.suite == "bug_fix"
    assert report.verdict == "pass"
    assert len(report.results) == 1
    assert report.results[0].case_id == "lockout"
