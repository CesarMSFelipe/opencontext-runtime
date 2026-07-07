"""AC-012 / AC-013: TDD strict — no RED, no pass; RED → GREEN demonstrated.

Contracts: TDD_STRICT_CONTRACT.md, RUN_STATE_CONTRACT.md.
"""

from __future__ import annotations

import json

import pytest

from tests.acceptance.helpers.cli import run_json
from tests.acceptance.helpers.ops import (
    WORKFLOW_TIMEOUT,
    find_run_dir,
    index_workspace,
    install_workspace,
)
from tests.acceptance.helpers.workspace import CORRECT_ADD_EDITS

pytestmark = pytest.mark.acceptance


@pytest.mark.smoke
def test_tdd_strict_fails_without_red_test(oc_bin, workspace) -> None:
    """AC-012: TDD strict fails when there is no RED test."""
    ws = workspace("py_bugfix_no_tests")
    ws.write_stub_provider(CORRECT_ADD_EDITS)
    install_workspace(oc_bin, ws)
    ws.set_tdd_mode("strict")
    index_workspace(oc_bin, ws)

    proc, summary = run_json(
        oc_bin,
        ["run", "Fix the subtraction bug in add in app.py", "--json"],
        cwd=ws.root,
        env=ws.env,
        timeout=WORKFLOW_TIMEOUT,
    )
    # No test runner evidence is possible here, so a strict run may not pass.
    assert summary.get("status") not in {"passed", "completed"}, (
        f"TDD_STRICT_CONTRACT: no RED test was ever executed, yet the strict run "
        f"reported {summary.get('status')!r} with "
        f"verification_outcome={summary.get('verification_outcome')!r}"
    )
    assert proc.returncode == 6, f"TDD strict violations must exit 6, got {proc.returncode}"


def test_tdd_red_green_demonstrated_externally(stub_run) -> None:
    """AC-013: TDD strict passes only with RED → GREEN demonstrated (external evidence)."""
    # RED: the seeded test genuinely failed BEFORE the run.
    red = stub_run["red"]
    assert red.returncode != 0, "fixture must start RED (seeded failing test)"
    assert "test_add" in red.stdout, red.stdout[-800:]

    # The run then mutated the code and its own verification passed.
    assert stub_run["summary"].get("verification_outcome") == "passed"

    # GREEN: the same test genuinely passes AFTER the run.
    green = stub_run["green"]
    assert green.returncode == 0, f"GREEN not reached after the run: {green.stdout[-800:]}"


def test_run_report_records_red_green_evidence(stub_run) -> None:
    """AC-013: the run report records machine-verified RED and GREEN evidence."""
    ws = stub_run["ws"]
    run_dir = find_run_dir(ws, stub_run["summary"]["run_id"])
    candidates = [run_dir / "run.json", run_dir / "state.json"]
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in candidates if p.is_file()]
    assert reports, f"no run report found in {run_dir}"
    tdd_blocks = [r.get("tdd") for r in reports if isinstance(r, dict) and r.get("tdd")]
    assert tdd_blocks, "run report must persist a tdd block (TDD_STRICT_CONTRACT)"
    tdd = tdd_blocks[0]
    assert tdd.get("red_proven") is True
    assert tdd.get("green_proven") is True
    assert tdd.get("red", {}).get("command"), "RED evidence must name its command"
    assert tdd.get("green", {}).get("command"), "GREEN evidence must name its command"
