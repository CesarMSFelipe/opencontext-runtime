"""Tests for estimate + recommend_workflow (SPEC MP-007)."""

from __future__ import annotations

from opencontext_core.planning.decomposition import ImplementationSlice
from opencontext_core.planning.estimates import estimate, recommend_workflow
from opencontext_core.planning.program import MetaPlanner


def _slice(requirement_ids: list[str]) -> ImplementationSlice:
    return ImplementationSlice(slice_id="slice-x", title="X", requirement_ids=requirement_ids)


def test_low_risk_bugfix_single_requirement_recommends_oc_flow() -> None:
    planner = MetaPlanner()
    slice = _slice(["R1"])
    planner.assess(slice, task_type="bugfix", risk_level="low")  # -> level "cheap"
    planner.estimate(slice)

    assert slice.recommended_workflow == "oc-flow"
    assert slice.estimate  # populated
    assert slice.estimate["effort"] == "small"


def test_high_risk_slice_recommends_sdd() -> None:
    planner = MetaPlanner()
    slice = _slice(["R1", "R2", "R3"])
    planner.assess(slice, task_type="security", risk_level="high")  # -> "critical"
    result = planner.estimate(slice)

    assert slice.recommended_workflow == "sdd"
    assert result["loc"] > 0
    assert result["review_units"] >= 1


def test_module_level_helpers_are_consistent() -> None:
    slice = _slice(["R1"])
    # Without a risk assessment, the default level is "precise" -> sdd.
    assert recommend_workflow(slice) == "sdd"
    est = estimate(slice)
    assert est["requirement_count"] == 1
    assert est["risk_level"] == "precise"
