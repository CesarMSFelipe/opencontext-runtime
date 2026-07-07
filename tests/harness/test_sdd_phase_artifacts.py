"""SDD-003 / SDD-004 / SDD-005 / SDD-006 — harness SDD phases consume and
produce connected artifacts.

Pins the explore→propose exploration handoff, the spec's proposal dependency +
acceptance artifact, design traceability back to spec requirements, and the
executable (file-mapped) task breakdown. SDD_CONTRACT.md: no phase may print
placeholders reported as success or lose artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import (
    DesignPhase,
    ExplorePhase,
    ProposePhase,
    SpecPhase,
    TasksPhase,
)
from opencontext_core.harness.runner import HarnessRunner


def _runner_state(tmp_path: Path, task: str = "add farewell greeting"):
    runner = HarnessRunner(root=tmp_path)
    state = runner.create_run("sdd", task)
    return runner, state


def _run_dir(tmp_path: Path, state) -> Path:
    run_dir = tmp_path / ".opencontext" / "runs" / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


# ---------------------------------------------------------------------------
# SDD-003 — explore persists exploration.md; propose consumes it
# ---------------------------------------------------------------------------


def test_explore_persists_exploration_artifact(tmp_path: Path) -> None:
    """SDD-003: ExplorePhase persists exploration.md so the propose phase has a
    concrete exploration artifact to read (SDD_CONTRACT Current→Target addition)."""
    (tmp_path / "app.py").write_text(
        'def greet(name):\n    return "hello " + name\n', encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

    runner, state = _runner_state(tmp_path)
    cfg = runner.config.phases.get("explore")
    result = ExplorePhase(cfg, BudgetMode.OFF).run(state)

    exploration = tmp_path / ".opencontext" / "runs" / state.run_id / "exploration.md"
    assert exploration.is_file(), "explore must persist exploration.md"
    text = exploration.read_text(encoding="utf-8")
    assert text.startswith("# Exploration:")
    assert state.task in text
    assert any(a.kind == "exploration" for a in result.artifacts)


def test_propose_consumes_exploration_artifact(tmp_path: Path) -> None:
    """SDD-003: ProposePhase reads exploration.md and carries its content into
    proposal.json — the explore→propose handoff is load-bearing, not decorative."""
    runner, state = _runner_state(tmp_path)
    run_dir = _run_dir(tmp_path, state)
    marker = "EXPLORATION-MARKER-7f3a"
    (run_dir / "exploration.md").write_text(
        f"# Exploration: {state.task}\n\n- finding: {marker}\n", encoding="utf-8"
    )

    cfg = runner.config.phases.get("propose")
    ProposePhase(cfg, BudgetMode.OFF).run(state)

    proposal = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    assert proposal["exploration"]["path"].endswith("exploration.md")
    assert marker in proposal["exploration"]["digest"]
    assert proposal["evidence"]["exploration_md"].endswith("exploration.md")


# ---------------------------------------------------------------------------
# SDD-004 — spec consumes the proposal and produces acceptance
# ---------------------------------------------------------------------------


def test_spec_fails_closed_when_proposal_missing(tmp_path: Path) -> None:
    """SDD-004: SpecPhase fails (never scaffolds) when proposal.json is missing —
    each phase consumes the previous phase's artifact."""
    runner, state = _runner_state(tmp_path)
    cfg = runner.config.phases.get("spec")
    result = SpecPhase(cfg, BudgetMode.OFF).run(state)

    assert result.status == GateStatus.FAILED
    assert result.metadata["error"] == "Proposal artifact missing"
    assert not (tmp_path / ".opencontext" / "runs" / state.run_id / "spec.md").exists()


def test_spec_produces_acceptance_artifact(tmp_path: Path) -> None:
    """SDD-004: SpecPhase reads the proposal and produces acceptance.md carrying
    the spec's GIVEN/WHEN/THEN acceptance scenarios."""
    runner, state = _runner_state(tmp_path)
    run_dir = _run_dir(tmp_path, state)
    (run_dir / "proposal.json").write_text(
        json.dumps({"task": state.task, "approach": {"method": "incremental"}}),
        encoding="utf-8",
    )

    cfg = runner.config.phases.get("spec")
    result = SpecPhase(cfg, BudgetMode.OFF).run(state)

    acceptance = run_dir / "acceptance.md"
    assert acceptance.is_file(), "spec must persist acceptance.md"
    text = acceptance.read_text(encoding="utf-8")
    assert "Scenario" in text, "acceptance.md must carry the spec scenarios"
    assert any(a.kind == "acceptance" for a in result.artifacts)
    # The canonical spec artifact stays first (existing pins index artifacts[0]).
    assert result.artifacts[0].kind == "spec"


# ---------------------------------------------------------------------------
# SDD-005 — design is traceable back to the spec requirements
# ---------------------------------------------------------------------------


def test_design_traces_spec_requirements(tmp_path: Path) -> None:
    """SDD-005: DesignPhase output carries a Traceability section naming the spec
    requirements the design satisfies."""
    runner, state = _runner_state(tmp_path)
    run_dir = _run_dir(tmp_path, state)
    (run_dir / "spec.md").write_text(
        "# Delta Spec: farewell\n\n## ADDED Requirements\n\n"
        "### Requirement: Farewell Returns Goodbye\n\n"
        'farewell(name) SHALL return "goodbye " + name.\n\n'
        '#### Scenario: basic farewell\n\n- WHEN farewell("bob") is called\n'
        '- THEN it returns "goodbye bob"\n',
        encoding="utf-8",
    )

    cfg = runner.config.phases.get("design")
    DesignPhase(cfg, BudgetMode.OFF).run(state)

    design = (run_dir / "design.md").read_text(encoding="utf-8")
    assert "## Traceability" in design, "design must carry a Traceability section"
    assert "Farewell Returns Goodbye" in design, "design must name the spec requirement"


# ---------------------------------------------------------------------------
# SDD-006 — tasks are executable (every task maps to files)
# ---------------------------------------------------------------------------


def test_tasks_maps_every_task_to_files(tmp_path: Path) -> None:
    """SDD-006: TasksPhase produces executable tasks — every task maps to
    concrete file paths, and a test-first task is always included."""
    runner, state = _runner_state(tmp_path)
    run_dir = _run_dir(tmp_path, state)
    (run_dir / "design.md").write_text(
        "# Design\n\n## Files to Create/Modify\n\n- app.py\n- lib/util.py\n",
        encoding="utf-8",
    )

    cfg = runner.config.phases.get("tasks")
    TasksPhase(cfg, BudgetMode.OFF).run(state)

    payload = json.loads((run_dir / "tasks.json").read_text(encoding="utf-8"))
    tasks = payload["tasks"]
    assert tasks, "tasks.json must contain a task breakdown"
    assert all(t["file_paths"] for t in tasks), f"unmapped (non-executable) task in {tasks}"
    mapped = {p for t in tasks for p in t["file_paths"]}
    assert "app.py" in mapped and "lib/util.py" in mapped
    assert any(t["id"] == "task-test" for t in tasks), "a test-first task is required"
