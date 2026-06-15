"""Tests that HarnessRunner schedules phases via the folded DAG, not a list.

the single orchestration spine. `HarnessRunner` MUST schedule
phases via the folded `PHASE_DEPENDENCIES` / `WORKFLOW_TRACKS` DAG (dependency
resolution + track selection) instead of the previously hardcoded
``phase_ids`` list.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.agents.sdd_orchestrator import (
    PHASE_DEPENDENCIES,
    WORKFLOW_TRACKS,
)
from opencontext_core.harness.runner import HarnessRunner


def _topologically_valid(phases: list[str], deps: dict[str, list[str]]) -> bool:
    """Every phase's declared (in-track) deps precede it in the sequence."""
    seen: set[str] = set()
    for phase in phases:
        for dep in deps.get(phase, []):
            if dep in phases and dep not in seen:
                return False
        seen.add(phase)
    return True


class TestPhaseScheduling:
    def test_runner_exposes_dag_scheduler(self, tmp_path: Path) -> None:
        """The runner owns a DAG scheduler method (the single live spine)."""
        runner = HarnessRunner(root=tmp_path)
        assert callable(getattr(runner, "schedule_phases", None))

    def test_sdd_workflow_uses_full_track_dag(self, tmp_path: Path) -> None:
        """`sdd` resolves to the full track, in dependency order from the DAG."""
        runner = HarnessRunner(root=tmp_path)
        scheduled = runner.schedule_phases("sdd")

        full_phases = WORKFLOW_TRACKS["full"]["phases"]
        assert isinstance(full_phases, list)
        # Same membership as the declared full track.
        assert set(scheduled) == set(full_phases)
        # Resolved through PHASE_DEPENDENCIES (topologically valid order).
        assert _topologically_valid(scheduled, PHASE_DEPENDENCIES)
        # Dependency ordering is real, not the incidental old hardcoded order's
        # accident: explore precedes propose precedes spec precedes apply.
        assert scheduled.index("explore") < scheduled.index("propose")
        assert scheduled.index("propose") < scheduled.index("spec")
        assert scheduled.index("apply") < scheduled.index("verify")

    def test_standard_track_selection(self, tmp_path: Path) -> None:
        """Track selection: a `standard`-track workflow yields the standard phases.

        Proves the scheduler honors WORKFLOW_TRACKS (track selection), not a
        single hardcoded phase list.
        """
        runner = HarnessRunner(root=tmp_path)
        scheduled = runner.schedule_phases("standard")

        track = WORKFLOW_TRACKS["standard"]
        track_phases = track["phases"]
        track_deps = track["deps"]
        assert isinstance(track_phases, list)
        assert isinstance(track_deps, dict)

        assert set(scheduled) == set(track_phases)
        # propose/tasks/archive/review are NOT in the standard track.
        assert "propose" not in scheduled
        assert "tasks" not in scheduled
        # Order respects the standard track's own dependency map.
        assert _topologically_valid(scheduled, track_deps)  # type: ignore[arg-type]

    def test_quick_track_selection(self, tmp_path: Path) -> None:
        """`quick` track resolves to explore -> apply -> verify only."""
        runner = HarnessRunner(root=tmp_path)
        scheduled = runner.schedule_phases("quick")
        assert scheduled == ["explore", "apply", "verify"]

    def test_unsatisfiable_in_set_dependency_is_dropped(self, tmp_path: Path) -> None:
        """A phase whose in-set deps can never complete (a cycle) is dropped.

        Dependency resolution must not emit a phase out of order: a cyclic pair
        is genuinely unsatisfiable within the set, so both are excluded while an
        independent phase still schedules.
        """
        runner = HarnessRunner(root=tmp_path)
        phases = ["explore", "a", "b"]
        deps = {"explore": [], "a": ["b"], "b": ["a"]}  # a<->b cycle
        scheduled = runner.resolve_dag(phases, deps)
        assert "explore" in scheduled
        assert "a" not in scheduled  # cyclic dependency → not scheduled
        assert "b" not in scheduled

    def test_out_of_set_dependency_is_ignored(self, tmp_path: Path) -> None:
        """Deps that point outside the requested set are ignored, not blocking.

        This is what lets ``apply-only`` run apply/verify/archive without their
        full-DAG upstream phases (tasks, spec, ...) being present.
        """
        runner = HarnessRunner(root=tmp_path)
        scheduled = runner.schedule_phases("apply-only")
        assert scheduled == ["apply", "verify", "archive"]

    def test_run_executes_in_dag_order(self, tmp_path: Path) -> None:
        """An end-to-end sdd run executes phases in the DAG-resolved order.

        Regression guard against reverting to the hardcoded ``phase_ids`` list:
        the executed ledger/phase order must match the scheduler output.
        """
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        from opencontext_core.harness.models import BudgetMode

        runner = HarnessRunner(root=tmp_path)
        expected = runner.schedule_phases("sdd")
        result = runner.run("sdd", "scheduling task", BudgetMode.OFF)

        executed = [ledger.phase for ledger in result.ledgers]
        # Executed phases must EQUAL the DAG schedule restricted to the phases that
        # actually ran, in that exact order — not merely be monotonic (two phases
        # are trivially sorted, hiding a scheduler that dropped the middle six).
        assert executed == [p for p in expected if p in set(executed)], (
            f"executed order {executed} != DAG schedule {expected} filtered to executed"
        )
        assert len(executed) == len(set(executed)), f"a phase ran more than once: {executed}"
        assert executed[0] == expected[0]  # the entry phase (explore) ran first
