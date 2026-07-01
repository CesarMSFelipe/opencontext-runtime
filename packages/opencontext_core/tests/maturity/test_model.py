"""Tests for maturity-model (PR-R2-F).

REQ-maturity-001..004 — 6-level scoring + assessment.
"""

from __future__ import annotations


class TestMaturityLevel:
    def test_six_levels(self) -> None:
        from opencontext_core.maturity.model import MaturityLevel

        levels = [m.name for m in MaturityLevel]
        assert levels == [
            "L0_NOT_STARTED",
            "L1_EXPERIMENTAL",
            "L2_OPERATIONAL",
            "L3_PRODUCTION",
            "L4_OPTIMIZED",
            "L5_MEASURABLE",
        ]

    def test_levels_are_int_subclass(self) -> None:
        from opencontext_core.maturity.model import MaturityLevel

        assert int(MaturityLevel.L0_NOT_STARTED) == 0
        assert int(MaturityLevel.L5_MEASURABLE) == 5


class TestAssessMaturity:
    def test_empty_assessment_is_level_zero(self) -> None:
        from opencontext_core.maturity.model import assess_maturity

        report = assess_maturity({})
        assert report.overall_level == 0
        # No dimensions supplied => report still has the 12-dim skeleton, all L0
        assert len(report.dimensions) == 12

    def test_overall_is_min_of_dimensions(self) -> None:
        from opencontext_core.maturity.model import (
            MaturityLevel,
            assess_maturity,
        )

        levels = {dim: MaturityLevel.L3_PRODUCTION for dim in [
            "kg", "memory", "context", "cache", "intelligence",
            "provider", "plugin", "marketplace", "studio",
            "benchmark", "observability", "data_gov",
        ]}
        # Knock data_gov down to L1
        levels["data_gov"] = MaturityLevel.L1_EXPERIMENTAL
        report = assess_maturity(levels)
        assert report.overall_level == 1
        assert "data_gov" in report.missing_capabilities or report.missing_capabilities

    def test_recommended_next_is_runnable(self) -> None:
        from opencontext_core.maturity.model import assess_maturity

        report = assess_maturity({})
        assert report.recommended_next, "fresh install must yield >=1 runnable next step"
        for step in report.recommended_next:
            assert step.command.startswith("opencontext ")
            assert step.roadmap_link.startswith("docs/roadmap/")

    def test_assessment_dataclass_serializable(self) -> None:
        from opencontext_core.maturity.model import (
            MaturityAssessment,
            assess_maturity,
        )

        report = assess_maturity({})
        assert isinstance(report, MaturityAssessment)
        d = report.to_dict()
        assert "overall_level" in d
        assert "dimensions" in d
        assert "missing_capabilities" in d
        assert "recommended_next" in d

    def test_data_gov_zero_flags_missing(self) -> None:
        """REQ-maturity-001 — worst dimension bottlenecks the team."""
        from opencontext_core.maturity.model import (
            MaturityLevel,
            assess_maturity,
        )

        levels = {dim: MaturityLevel.L4_OPTIMIZED for dim in [
            "kg", "memory", "context", "cache", "intelligence",
            "provider", "plugin", "marketplace", "studio",
            "benchmark", "observability",
        ]}
        levels["data_gov"] = MaturityLevel.L0_NOT_STARTED
        report = assess_maturity(levels)
        assert report.overall_level == 0
        assert any("data_gov" in cap for cap in report.missing_capabilities)

    def test_unknown_dimension_ignored(self) -> None:
        """Unknown dimensions don't crash — they're skipped silently."""
        from opencontext_core.maturity.model import assess_maturity

        report = assess_maturity({"some_random_dim": 99})  # type: ignore[dict-item]
        assert report.overall_level == 0
