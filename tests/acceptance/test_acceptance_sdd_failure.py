"""SDD-008: the SDD workflow run fails honestly when the project's tests fail.

Contracts: SDD_CONTRACT.md (`verify` uses the real verification engine; failing
apply/verify gates enter the `failed` state, exit code 8) and
RUN_STATE_CONTRACT.md (canonical states + exit codes). Mirrors AC-016's real
`run --workflow sdd` path with a deliberately WRONG edit that breaks the
fixture's test suite.
"""

from __future__ import annotations

import json

import pytest

from tests.acceptance.helpers.cli import run_json
from tests.acceptance.helpers.ops import (
    WORKFLOW_TIMEOUT,
    find_flat_run_dir,
    index_workspace,
    install_workspace,
)

pytestmark = pytest.mark.acceptance

#: Deterministic WRONG ApplyEdit set: breaks greet() so tests/test_app.py fails.
_WRONG_GREET_EDITS = [
    {
        "path": "app.py",
        "operation": "replace_range",
        "start_line": 5,
        "end_line": 5,
        "content": '    return "goodbye " + name',
        "reason": "intentionally wrong edit for the SDD failing-verification scenario",
        "requirement_refs": ["greet returns a hello greeting"],
    }
]


@pytest.fixture(scope="module")
def sdd_failing_run(oc_bin, tmp_path_factory):
    """One shared SDD workflow run whose stub executor applies a WRONG edit."""
    from tests.acceptance.helpers.workspace import make_workspace

    ws = make_workspace(tmp_path_factory.mktemp("sdd-fail"), "sdd_feature_basic")
    ws.write_stub_provider(_WRONG_GREET_EDITS)
    install_workspace(oc_bin, ws)
    index_workspace(oc_bin, ws)
    proc, summary = run_json(
        oc_bin,
        ["run", "Change the greeting message", "--workflow", "sdd", "--json"],
        cwd=ws.root,
        env=ws.env,
        timeout=WORKFLOW_TIMEOUT,
    )
    return ws, proc, summary


def test_sdd_workflow_fails_when_tests_fail(sdd_failing_run) -> None:
    """SDD-008: `run --workflow sdd` reports a failed run (never success) with a
    non-zero exit code when the applied edit breaks the project's tests, and the
    run persists the FAILED verify-phase gate as evidence in gates.json.

    One consolidated scenario (ACCEPTANCE_CONTRACT full-lane size budget)."""
    ws, proc, summary = sdd_failing_run
    assert summary.get("workflow") == "sdd", summary
    assert summary.get("status") not in {"passed", "completed"}, (
        f"SDD_CONTRACT: failing tests must fail the run, got {summary.get('status')!r}"
    )
    assert summary.get("status") == "failed", summary
    assert proc.returncode in (1, 8), f"expected exit 1 or 8, got {proc.returncode}"

    # Gate evidence: gates.json records the failing test suite as a FAILED
    # verify-phase gate (never a silently-passed run).
    run_dir = find_flat_run_dir(ws, summary["run_id"])
    gates = json.loads((run_dir / "gates.json").read_text(encoding="utf-8"))["gates"]
    verify_gates = [g for g in gates if g.get("phase") == "verify"]
    assert verify_gates, f"no verify gates recorded: {gates}"
    assert any(g.get("status") == "failed" for g in verify_gates), (
        f"SDD verify must record the failing tests as a FAILED gate: {verify_gates}"
    )
