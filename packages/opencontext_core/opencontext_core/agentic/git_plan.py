"""Git work plan — models and planner for branch/PR strategy.

GitWorkPlanner produces a GitWorkPlan from a change-id, task list, and GitMode.
No git commands are executed here; this is purely a planning module.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from opencontext_core.agentic.config import GitMode


class GitWorkUnit(BaseModel, extra="forbid"):
    """A single unit of git work (one branch + one PR)."""

    branch_name: str
    pr_title: str
    tasks: list[str] = Field(default_factory=list)
    base_branch: str = "main"
    description: str = ""


class GitWorkPlan(BaseModel, extra="forbid"):
    """A complete git work plan for a change."""

    schema_version: str = "opencontext.git_work_plan.v1"
    mode: GitMode
    base_branch: str = "main"
    work_units: list[GitWorkUnit] = Field(default_factory=list)
    apply_git_changes: bool = False


class GitWorkPlanner:
    """Produces a GitWorkPlan for a given change without executing any git commands."""

    def plan(
        self,
        *,
        change_id: str,
        tasks: list[str],
        mode: GitMode,
        base_branch: str = "main",
    ) -> GitWorkPlan:
        """Return a GitWorkPlan for *change_id* and *tasks* under *mode*."""
        if mode == GitMode.SINGLE_PR:
            return self._single_pr(change_id, tasks, base_branch)
        if mode == GitMode.STACKED_PRS:
            return self._stacked_prs(change_id, tasks, base_branch)
        # GitMode.NONE or any future unknown mode — return an empty plan.
        return GitWorkPlan(mode=mode, base_branch=base_branch, apply_git_changes=False)

    def _single_pr(
        self, change_id: str, tasks: list[str], base_branch: str
    ) -> GitWorkPlan:
        unit = GitWorkUnit(
            branch_name=f"feat/{change_id}",
            pr_title=f"feat: {change_id}",
            tasks=list(tasks),
            base_branch=base_branch,
        )
        return GitWorkPlan(
            mode=GitMode.SINGLE_PR,
            base_branch=base_branch,
            work_units=[unit],
            apply_git_changes=True,
        )

    def _stacked_prs(
        self, change_id: str, tasks: list[str], base_branch: str
    ) -> GitWorkPlan:
        units: list[GitWorkUnit] = []
        prev_branch = base_branch
        for i, task in enumerate(tasks, start=1):
            branch = f"feat/{change_id}/part-{i}"
            units.append(
                GitWorkUnit(
                    branch_name=branch,
                    pr_title=f"feat({change_id}): part {i} — {task[:60]}",
                    tasks=[task],
                    base_branch=prev_branch,
                )
            )
            prev_branch = branch
        return GitWorkPlan(
            mode=GitMode.STACKED_PRS,
            base_branch=base_branch,
            work_units=units,
            apply_git_changes=True,
        )


if __name__ == "__main__":
    import pydantic

    planner = GitWorkPlanner()

    none_plan = planner.plan(change_id="test", tasks=["t1"], mode=GitMode.NONE)
    assert none_plan.work_units == []
    assert not none_plan.apply_git_changes

    single = planner.plan(change_id="add-health", tasks=["task1", "task2"], mode=GitMode.SINGLE_PR)
    assert len(single.work_units) == 1
    assert single.work_units[0].branch_name == "feat/add-health"

    stacked = planner.plan(change_id="my-change", tasks=["a", "b"], mode=GitMode.STACKED_PRS)
    assert len(stacked.work_units) == 2

    try:
        GitWorkPlan(mode=GitMode.NONE, bad_field="oops")  # type: ignore[call-arg]
        raise AssertionError("Expected ValidationError")
    except pydantic.ValidationError:
        pass

    print("agentic/git_plan.py self-check passed.")
