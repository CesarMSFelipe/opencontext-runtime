"""Tests for ProgramPlan + ConvergenceMap + MetaPlanner.build (SPEC MP-001/008/009/010)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.agentic.receipt import AgenticReceipt
from opencontext_core.agents.artifact_store import OpenSpecStore
from opencontext_core.planning.program import (
    ARTIFACT_KIND_CONVERGENCE_MAP,
    ARTIFACT_KIND_PROGRAM_PLAN,
    CHANGE_ID,
    ConvergenceMap,
    Disposition,
    MetaPlanner,
    PlanningError,
    ProgramPlan,
)

# The _INDEX-refined-runtime-vnext.md program: 17 main PRs + 5 foundational = 22.
PROGRAM_22_PRS: list[str] = [
    "001", "002", "003", "004", "005", "006", "007", "008", "009",
    "010", "011", "012", "013", "014", "015", "016", "017",
    "000", "000.1", "000.2", "000.3", "000.4",
]


def test_facade_exposes_required_methods() -> None:
    planner = MetaPlanner()
    for name in ("parse_intent", "decompose", "assign_prs", "assess", "estimate", "build"):
        assert callable(getattr(planner, name)), name


def test_build_produces_plan_with_slices_and_convergence() -> None:
    plan = MetaPlanner().build(
        intent="governed runtime program", requirements=["MP-001", "MP-002"], persist=False
    )
    assert isinstance(plan, ProgramPlan)
    assert plan.schema_version == "opencontext.program_plan.v1"
    assert len(plan.slices) >= 1
    assert isinstance(plan.convergence, ConvergenceMap)
    assert plan.convergence.entries


def test_every_requirement_has_a_disposition() -> None:
    requirements = ["R1", "R2", "R3", "R4"]
    plan = MetaPlanner().build(
        intent="cover everything",
        requirements=requirements,
        deferred={"R3": "1.x"},
        rejected={"R4": "out of scope for 1.0"},
        persist=False,
    )
    entries = {e.requirement_id: e for e in plan.convergence.entries}
    assert set(entries) == set(requirements)
    assert all(e.disposition in set(Disposition) for e in entries.values())
    assert entries["R3"].disposition is Disposition.deferred
    assert entries["R3"].target == "1.x"
    assert entries["R4"].disposition is Disposition.rejected
    assert entries["R4"].reason == "out of scope for 1.0"
    assert entries["R1"].disposition is Disposition.assigned
    assert entries["R1"].pr_id


def test_22_pr_program_has_zero_orphans() -> None:
    plan = MetaPlanner().build(
        intent="Mutate OpenContext into a governed engineering runtime "
        "over the roadmap, backlog and convergence matrix.",
        requirements=PROGRAM_22_PRS,
        persist=False,
    )
    assert plan.convergence.orphans(PROGRAM_22_PRS) == []
    assert len(plan.convergence.entries) == len(PROGRAM_22_PRS)
    assert all(
        e.disposition is Disposition.assigned and e.pr_id
        for e in plan.convergence.entries
    )


def test_orphan_requirement_fails_the_build_and_is_named() -> None:
    # The blank requirement is dropped by decompose and is not deferred/rejected.
    with pytest.raises(PlanningError) as excinfo:
        MetaPlanner().build(
            intent="leak one", requirements=["R1", "   "], persist=False
        )
    assert "orphan" in str(excinfo.value).lower()


def test_human_decomposition_missing_a_requirement_is_an_orphan() -> None:
    from opencontext_core.planning.decomposition import ImplementationSlice

    # Caller-provided slices cover only R1; R2 is in requirements but unassigned.
    slices = [ImplementationSlice(slice_id="slice-a", title="A", requirement_ids=["R1"])]
    with pytest.raises(PlanningError) as excinfo:
        MetaPlanner().build(
            intent="verify coverage",
            requirements=["R1", "R2"],
            slices=slices,
            persist=False,
        )
    assert "R2" in str(excinfo.value)


def test_reasoned_rejection_passes() -> None:
    plan = MetaPlanner().build(
        intent="reject with reason",
        requirements=["R1"],
        rejected={"R1": "superseded by PR-002 store rewrite"},
        persist=False,
    )
    entry = plan.convergence.entries[0]
    assert entry.disposition is Disposition.rejected
    assert entry.reason == "superseded by PR-002 store rewrite"


def test_rejection_without_reason_fails() -> None:
    with pytest.raises(PlanningError):
        MetaPlanner().build(
            intent="bad rejection", requirements=["R1"], rejected={"R1": ""}, persist=False
        )


def test_persist_true_writes_artifact_and_produces_receipt(tmp_path: Path) -> None:
    store = OpenSpecStore(root=tmp_path)
    planner = MetaPlanner(store=store)
    plan = planner.build(intent="persist me", requirements=["R1", "R2"], persist=True)

    change_dir = tmp_path / "changes" / CHANGE_ID
    assert (change_dir / f"{ARTIFACT_KIND_PROGRAM_PLAN}.md").exists()
    assert (change_dir / f"{ARTIFACT_KIND_CONVERGENCE_MAP}.md").exists()

    assert isinstance(planner.last_receipt, AgenticReceipt)
    assert planner.last_receipt.change_id == CHANGE_ID
    assert planner.last_receipt.run_id == plan.program_id


def test_persist_false_leaves_store_untouched(tmp_path: Path) -> None:
    store = OpenSpecStore(root=tmp_path)
    planner = MetaPlanner(store=store)
    planner.build(intent="in memory", requirements=["R1"], persist=False)

    assert not (tmp_path / "changes").exists()
    assert planner.last_receipt is None


def test_persist_true_without_store_raises() -> None:
    with pytest.raises(PlanningError):
        MetaPlanner().build(intent="no store", requirements=["R1"], persist=True)
