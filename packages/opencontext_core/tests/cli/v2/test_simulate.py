"""REQ-cli-v2-001: simulate returns a SimulationReport-shaped dict."""

from __future__ import annotations

from opencontext_cli.commands.v2.simulate import build_simulation_report


def test_REQ_cli_v2_001_simulate_report() -> None:
    report = build_simulation_report(
        task="ship feature X",
        proposed_path=["explore", "spec", "apply"],
        estimated_tokens=1200,
        estimated_cost=0.04,
        estimated_duration_ms=30000,
        estimator="stub",
    )
    assert report["task"] == "ship feature X"
    assert report["proposed_path"] == ["explore", "spec", "apply"]
    assert report["estimated_tokens"] == 1200
    assert report["estimated_cost"] == 0.04
    assert report["estimated_duration_ms"] == 30000
    assert report["estimator"] == "stub"
    assert "schema_version" in report


def test_simulate_report_minimal_fields() -> None:
    report = build_simulation_report(task="t", proposed_path=["a"])
    for key in ("task", "proposed_path", "estimator"):
        assert key in report