"""Tests for verification checks, including P3.5 harness/adapter checks."""

from __future__ import annotations

from opencontext_core.verification import (
    CheckResult,
    VerificationReport,
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
    def test_all_nine_phases_available(self) -> None:
        result = check_harness_phases()
        assert result.status == "passed"
        assert "9/9" in result.message
        assert "explore" in result.message
        assert "propose" in result.message
        assert "spec" in result.message
        assert "design" in result.message
        assert "tasks" in result.message
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

    def test_is_healthy_reflects_failures_and_kg_warning(self) -> None:
        """``is_healthy`` iff zero failures AND no Knowledge Graph warning.

        A Knowledge Graph warning degrades health (most OC features depend on the
        KG); other advisory warnings (e.g. Python version) do not. Exercised on
        synthetic reports so it never depends on the live machine's KG state,
        which is legitimately unindexed in CI / any fresh environment (that
        env-coupling is exactly what used to make this assertion flake).
        """
        # No failures, no KG warning -> healthy.
        healthy = VerificationReport(
            results=[CheckResult(name="Python Version", status="passed", message="ok")]
        )
        assert healthy.failures == 0
        assert healthy.is_healthy is True
        # A non-KG advisory warning does NOT degrade health.
        advisory = VerificationReport(
            results=[CheckResult(name="Python Version", status="warning", message="old")]
        )
        assert advisory.is_healthy is True
        # A Knowledge Graph warning DOES degrade health, even with zero failures.
        kg_degraded = VerificationReport(
            results=[CheckResult(name="Knowledge Graph", status="warning", message="no db")]
        )
        assert kg_degraded.failures == 0
        assert kg_degraded.is_healthy is False
        # Any failure degrades health.
        failing = VerificationReport(
            results=[CheckResult(name="Boundary Service", status="failed", message="down")]
        )
        assert failing.is_healthy is False
