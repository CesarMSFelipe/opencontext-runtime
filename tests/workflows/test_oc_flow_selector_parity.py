"""Shared workflow-selector parity (B6 / AVH-013).

``simulate`` and ``run --workflow auto`` MUST return the same workflow for the same
task — they consume the ONE shared selector, so disagreement is structurally
impossible. This pins the audit's failing case ("Redesign public API and migrate
schema") to SDD on BOTH surfaces and asserts zero disagreement across a task matrix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.context.planning.workflow_selector import select_workflow
from opencontext_core.oc_flow.cli import run_oc_flow_cli
from opencontext_core.oc_flow.runner import select_workflow as run_select_workflow
from opencontext_core.runtime_intelligence.simulator import RuntimeSimulator

# (task, expected workflow). >=2 architecture/SDD, >=2 bugfix/oc-flow, 1 ambiguous.
_MATRIX: tuple[tuple[str, str], ...] = (
    # the audit's failing case — must be SDD on both surfaces
    ("Redesign public API and migrate schema", "sdd"),
    ("Redesign the authentication architecture", "sdd"),
    ("migrate the database schema to version 2", "sdd"),
    ("patch the SQL injection vulnerability", "sdd"),
    ("Fix failing test in tests/unit/test_parser.py", "oc-flow"),
    ("fix a lint error in one module", "oc-flow"),
    ("update the helper", "oc-flow"),  # ambiguous → fast operational default
)


@pytest.mark.parametrize("task,expected", _MATRIX)
def test_simulate_and_run_auto_agree(task: str, expected: str) -> None:
    sim = RuntimeSimulator().simulate(task).recommended_workflow
    run = run_select_workflow(task)
    shared = select_workflow(task).workflow
    assert sim == run == shared == expected, (
        f"workflow disagreement for {task!r}: simulate={sim} run={run} shared={shared}"
    )


# NOTE: the standalone "zero disagreements across matrix" test was cut — the
# parametrized test above already asserts sim == run for every matrix entry,
# so the aggregate check was a strict subset (redundant variation).


def test_run_auto_cli_recommends_sdd_for_redesign(tmp_path: Path) -> None:
    # The CLI `run --workflow auto` surface routes the audit's case to SDD.
    summary = run_oc_flow_cli(
        "Redesign public API and migrate schema",
        root=tmp_path,
        workflow="auto",
        enabled=True,
    )
    assert summary["status"] == "recommend_sdd"


def test_run_auto_cli_runs_oc_flow_for_localized_bugfix(tmp_path: Path) -> None:
    summary = run_oc_flow_cli(
        "Fix failing test in tests/unit/test_parser.py",
        root=tmp_path,
        workflow="auto",
        enabled=True,
    )
    assert summary["workflow"] == "oc-flow"
    assert summary["status"] != "recommend_sdd"
