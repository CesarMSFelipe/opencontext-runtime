"""REQ-cli-v2-001: doctor --runtime returns 11-dim HealthReport."""

from __future__ import annotations

from opencontext_cli.commands.v2.doctor_runtime import (
    HEALTH_DIMENSIONS,
    build_health_report,
)


def test_REQ_cli_v2_001_eleven_dims() -> None:
    assert len(HEALTH_DIMENSIONS) == 11


def test_build_health_report_shape() -> None:
    dims = {d: {"status": "ok", "detail": ""} for d in HEALTH_DIMENSIONS}
    report = build_health_report(dims)
    assert report["dimensions"] == dims
    assert "schema_version" in report
    assert len(report["dimensions"]) == 11
