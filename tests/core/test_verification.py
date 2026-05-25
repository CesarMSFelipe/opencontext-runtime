"""Tests for verification checks, including P3.5 harness/adapter checks."""

from __future__ import annotations

from opencontext_core.verification import (
    CheckResult,
    check_adapters,
    check_boundary_service,
    check_harness_phases,
    check_harness_runner,
    run_all_checks,
)


class TestCheckResult:
    def test_defaults(self) -> None:
        r = CheckResult(name="test", status="passed", message="ok")
        assert r.name == "test"
        assert r.status == "passed"
        assert r.message == "ok"
        assert r.details == ""


class TestHarnessPhasesCheck:
    def test_all_six_phases_available(self) -> None:
        result = check_harness_phases()
        assert result.status == "passed"
        assert "6/6" in result.message
        assert "explore" in result.message
        assert "propose" in result.message
        assert "apply" in result.message
        assert "verify" in result.message
        assert "review" in result.message
        assert "archive" in result.message


class TestHarnessRunnerCheck:
    def test_runner_instantiatable(self) -> None:
        result = check_harness_runner()
        assert result.status == "passed"
        assert "Runner ready" in result.message


class TestAdaptersCheck:
    def test_adapters_report(self) -> None:
        result = check_adapters()
        # local and python should always be available
        assert "local" in result.message
        assert "python" in result.message
        # status might be passed or warning depending on aider
        assert result.status in ("passed", "warning")


class TestBoundaryServiceCheck:
    def test_service_importable(self) -> None:
        result = check_boundary_service()
        assert result.status == "passed"
        assert "6 targets" in result.message


class TestRunAllChecks:
    def test_includes_new_checks(self) -> None:
        report = run_all_checks()
        check_names = [r.name for r in report.results]

        assert "Harness Phases" in check_names
        assert "Harness Runner" in check_names
        assert "Adapters" in check_names
        assert "Boundary Service" in check_names
        assert len(report.results) >= 11  # 7 original + 4 new

    def test_healthy_if_no_failures(self) -> None:
        """The report should be healthy if there are zero failures."""
        report = run_all_checks()
        # Warnings don't count as failures
        assert report.failures >= 0
        if report.failures == 0:
            assert report.is_healthy is True
