"""Tests for GitWorkPlan and GitWorkPlanner."""

from __future__ import annotations

import pytest
import pydantic

from opencontext_core.agentic.config import GitMode
from opencontext_core.agentic.git_plan import GitWorkPlan, GitWorkPlanner


def test_planner_returns_git_work_plan() -> None:
    planner = GitWorkPlanner()
    plan = planner.plan(change_id="add-health", tasks=["t1", "t2"], mode=GitMode.SINGLE_PR)
    assert isinstance(plan, GitWorkPlan)


def test_none_mode_returns_empty_plan() -> None:
    planner = GitWorkPlanner()
    plan = planner.plan(change_id="test", tasks=["t1"], mode=GitMode.NONE)
    assert plan.work_units == []
    assert not plan.apply_git_changes


def test_single_pr_produces_one_unit() -> None:
    planner = GitWorkPlanner()
    plan = planner.plan(change_id="my-change", tasks=["task1", "task2"], mode=GitMode.SINGLE_PR)
    assert len(plan.work_units) == 1
    assert "my-change" in plan.work_units[0].branch_name


def test_stacked_prs_produces_one_unit_per_task() -> None:
    tasks = ["task1", "task2", "task3"]
    planner = GitWorkPlanner()
    plan = planner.plan(change_id="stacked", tasks=tasks, mode=GitMode.STACKED_PRS)
    assert len(plan.work_units) == len(tasks)


def test_stacked_prs_chained_bases() -> None:
    planner = GitWorkPlanner()
    plan = planner.plan(
        change_id="chain", tasks=["a", "b", "c"], mode=GitMode.STACKED_PRS, base_branch="develop"
    )
    assert plan.work_units[0].base_branch == "develop"
    assert plan.work_units[1].base_branch == plan.work_units[0].branch_name
    assert plan.work_units[2].base_branch == plan.work_units[1].branch_name


def test_model_rejects_unknown_fields() -> None:
    with pytest.raises(pydantic.ValidationError):
        GitWorkPlan(mode=GitMode.NONE, unknown_field="bad")  # type: ignore[call-arg]


def test_schema_version_default() -> None:
    plan = GitWorkPlan(mode=GitMode.NONE)
    assert plan.schema_version == "opencontext.git_work_plan.v1"
