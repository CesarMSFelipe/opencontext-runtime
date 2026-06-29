"""Tests for PrPlan + assign_prs + acyclic graph check (SPEC MP-005)."""

from __future__ import annotations

import pytest

from opencontext_core.planning.decomposition import ImplementationSlice, decompose
from opencontext_core.planning.intent import parse_intent
from opencontext_core.planning.pr_plan import PrCycleError, PrPlan, assign_prs


def _slices() -> list[ImplementationSlice]:
    return decompose(parse_intent("plan it"), ["MP-001", "MP-002", "PR-003", "PR-004"])


def test_schema_version_is_pr_plan_v1() -> None:
    assert assign_prs(_slices()).schema_version == "opencontext.pr_plan.v1"


def test_every_slice_assigned_to_exactly_one_pr() -> None:
    slices = _slices()
    plan = assign_prs(slices)

    assignments: dict[str, int] = {}
    for pr in plan.prs:
        for slice_id in pr.slice_ids:
            assignments[slice_id] = assignments.get(slice_id, 0) + 1

    assert set(assignments) == {s.slice_id for s in slices}
    assert all(count == 1 for count in assignments.values())


def test_dependency_graph_is_acyclic_for_linear_chain() -> None:
    a = ImplementationSlice(slice_id="slice-a", title="A", requirement_ids=["R1"])
    b = ImplementationSlice(
        slice_id="slice-b", title="B", requirement_ids=["R2"], depends_on=["slice-a"]
    )
    plan = assign_prs([a, b])
    assert isinstance(plan, PrPlan)
    pr_b = next(p for p in plan.prs if "slice-b" in p.slice_ids)
    assert pr_b.depends_on == [plan.pr_for_slice("slice-a")]


def test_constructed_cycle_raises() -> None:
    a = ImplementationSlice(
        slice_id="slice-a", title="A", requirement_ids=["R1"], depends_on=["slice-b"]
    )
    b = ImplementationSlice(
        slice_id="slice-b", title="B", requirement_ids=["R2"], depends_on=["slice-a"]
    )
    with pytest.raises(PrCycleError):
        assign_prs([a, b])


def test_unknown_dependency_is_ignored() -> None:
    a = ImplementationSlice(
        slice_id="slice-a",
        title="A",
        requirement_ids=["R1"],
        depends_on=["slice-missing"],
    )
    plan = assign_prs([a])
    assert plan.prs[0].depends_on == []
