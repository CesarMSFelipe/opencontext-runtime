"""Tests for deep diagnostics module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.config import load_config
from opencontext_core.doctor.deep import (
    DeepDiagnostic,
    DeepReport,
    run_deep_diagnostics,
)


class TestDeepReport:
    """DeepReport data model tests."""

    def test_empty_report(self) -> None:
        """Empty report is healthy."""
        report = DeepReport(timestamp="2025-01-01T00:00:00")
        assert report.is_healthy
        assert report.passed == 0
        assert report.warnings == 0
        assert report.failures == 0
        assert report.all_checks == []
        assert report.to_dict()["healthy"] is True
        assert report.to_dict()["summary"]["total"] == 0

    def test_report_with_checks(self) -> None:
        """Report counts checks correctly."""
        report = DeepReport(timestamp="2025-01-01T00:00:00")
        report.system = [
            DeepDiagnostic(name="test.pass", status="passed", message="OK"),
            DeepDiagnostic(name="test.warn", status="warning", message="hmm"),
            DeepDiagnostic(name="test.fail", status="failed", message="broken"),
        ]
        assert report.passed == 1
        assert report.warnings == 1
        assert report.failures == 1
        assert not report.is_healthy
        assert len(report.all_checks) == 3

    def test_to_dict(self) -> None:
        """to_dict produces expected JSON-serializable structure."""
        report = DeepReport(timestamp="2025-01-01T00:00:00")
        report.system = [DeepDiagnostic(name="sys.ok", status="passed", message="all good")]
        report.verification = [
            DeepDiagnostic(
                name="verify.check",
                status="warning",
                message="something",
                details="more info",
                recommendation="fix it",
            )
        ]
        data = report.to_dict()
        assert data["timestamp"] == "2025-01-01T00:00:00"
        assert data["summary"]["passed"] == 1
        assert data["summary"]["warnings"] == 1
        assert data["sections"]["system"][0]["name"] == "sys.ok"
        assert data["sections"]["verification"][0]["recommendation"] == "fix it"
        # Ensure it's JSON-serializable
        serialized = json.dumps(data)
        assert isinstance(serialized, str)

    def test_diagnostic_variants(self) -> None:
        """All status values work correctly."""
        for status in ("passed", "warning", "failed", "error", "info"):
            d = DeepDiagnostic(name=f"test.{status}", status=status, message="msg")
            d_dict = DeepReport._diag_to_dict(d)
            assert d_dict["status"] == status


class TestDeepDiagnostics:
    """Integration tests — run deep diagnostics on real config."""

    def test_run_deep_diagnostics_structure(self) -> None:
        """run_deep_diagnostics returns a properly structured report."""
        config = load_config()
        report = run_deep_diagnostics(config)

        assert isinstance(report, DeepReport)
        assert report.timestamp
        assert len(report.system) > 0
        assert len(report.config) > 0
        assert len(report.verification) > 0
        # components may be empty if imports fail

    def test_system_section(self) -> None:
        """System section includes platform and Python info."""
        config = load_config()
        report = run_deep_diagnostics(config)

        names = {d.name for d in report.system}
        assert "os.platform" in names
        assert "python.version" in names
        assert "system.cpu" in names
        assert "system.disk" in names

    def test_verification_section(self) -> None:
        """Verification includes standard checks."""
        config = load_config()
        report = run_deep_diagnostics(config)

        names = {d.name for d in report.verification}
        assert "verify.python_version" in names
        assert "verify.user_config" in names
        assert "verify.disk_space" in names

    def test_config_section(self) -> None:
        """Config section includes security mode and features."""
        config = load_config()
        report = run_deep_diagnostics(config)

        names = {d.name for d in report.config}
        assert "config.security_mode" in names
        assert "config.features" in names
        assert "config.tools" in names

    def test_json_output(self) -> None:
        """to_dict output is valid for JSON serialization."""
        config = load_config()
        report = run_deep_diagnostics(config)
        data = report.to_dict()

        assert "timestamp" in data
        assert "healthy" in data
        assert "summary" in data
        assert "sections" in data
        assert "system" in data["sections"]
        assert isinstance(data["healthy"], bool)

        # Must be JSON-serializable
        blob = json.dumps(data)
        assert len(blob) > 0
        # Round-trip
        decoded = json.loads(blob)
        assert decoded["healthy"] == data["healthy"]
        assert decoded["summary"]["total"] == data["summary"]["total"]

    def test_healthy_flag(self) -> None:
        """healthy is True only when no failures."""
        report = DeepReport(timestamp="t")
        report.verification = [DeepDiagnostic(name="x", status="passed", message="ok")]
        assert report.is_healthy

        report.verification.append(DeepDiagnostic(name="y", status="failed", message="fail"))
        assert not report.is_healthy

        # warnings don't make it unhealthy
        report2 = DeepReport(timestamp="t")
        report2.verification = [
            DeepDiagnostic(name="w", status="warning", message="warn"),
            DeepDiagnostic(name="p", status="passed", message="ok"),
        ]
        assert report2.is_healthy
