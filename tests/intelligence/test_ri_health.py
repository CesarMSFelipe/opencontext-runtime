"""Runtime Health — 10 dimensions; degraded KG lowers overall (SPEC-RI-011-15)."""

from __future__ import annotations

from opencontext_core.indexing.graph_health import GraphHealthReport
from opencontext_core.models.intelligence import HEALTH_DIMENSIONS
from opencontext_core.runtime_intelligence.health import RuntimeHealth


def _health(status: str) -> GraphHealthReport:
    indexed = status not in ("empty", "unavailable")
    return GraphHealthReport(status=status, indexed=indexed, nodes=10)


def test_ten_dimensions_accounted_for(tmp_path) -> None:
    # Measured + unmeasured together cover exactly the ten declared dimensions, and
    # no dimension is ever reported as both measured and unmeasured (B9/AVH-016).
    report = RuntimeHealth().report(tmp_path, graph_health=_health("healthy"))
    covered = set(report.dimensions) | set(report.unmeasured_dimensions)
    assert covered == set(HEALTH_DIMENSIONS)
    assert not (set(report.dimensions) & set(report.unmeasured_dimensions))
    assert 0.0 <= report.overall_score <= 1.0


def test_kg_freshness_always_measured(tmp_path) -> None:
    # kg_freshness is a real read of the KG store status, so it is never UNMEASURED.
    report = RuntimeHealth().report(tmp_path, graph_health=_health("healthy"))
    assert "kg_freshness" in report.dimensions
    assert "kg_freshness" not in report.unmeasured_dimensions


def test_degraded_kg_lowers_freshness_and_overall(tmp_path) -> None:
    healthy = RuntimeHealth().report(tmp_path, graph_health=_health("healthy"))
    degraded = RuntimeHealth().report(tmp_path, graph_health=_health("degraded"))
    assert degraded.dimensions["kg_freshness"] < healthy.dimensions["kg_freshness"]
    assert degraded.overall_score < healthy.overall_score


def test_unavailable_kg_is_critical_finding(tmp_path) -> None:
    report = RuntimeHealth().report(tmp_path, graph_health=_health("unavailable"))
    assert "kg_freshness" in report.critical_findings


def test_unmeasured_dimensions_are_reported_not_fabricated(tmp_path) -> None:
    report = RuntimeHealth().report(tmp_path, graph_health=_health("healthy"))
    # No optional signals supplied → the other nine dims are UNMEASURED, listed
    # explicitly (not given a fabricated neutral 0.5 inside dimensions).
    assert "memory_quality" in report.unmeasured_dimensions
    assert "memory_quality" not in report.dimensions
    assert any("unmeasured" in rec for rec in report.recommendations)


def test_real_signals_become_measured_dimensions(tmp_path) -> None:
    # When real evidence is supplied, those dimensions move into `dimensions` and
    # the overall reflects only what was measured (B9/AVH-016).
    report = RuntimeHealth().report(
        tmp_path,
        graph_health=_health("healthy"),
        cost_error_pcts=[10.0, 20.0],  # → cost_calibration measured
        efficiency_all_sufficient=True,  # → benchmark_trend measured
    )
    assert "cost_calibration" in report.dimensions
    assert "benchmark_trend" in report.dimensions
    assert "cost_calibration" not in report.unmeasured_dimensions
