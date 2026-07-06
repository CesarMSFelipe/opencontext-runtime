"""AC-009 / AC-010 / AC-011: OC Flow honesty — executor states, mutation, verification.

Contracts: RUN_STATE_CONTRACT.md (canonical states + exit codes),
CLI_CONTRACT.md, ACCEPTANCE_CONTRACT.md.
"""

from __future__ import annotations

import pytest

from tests.acceptance.helpers.cli import run_json
from tests.acceptance.helpers.ops import (
    WORKFLOW_TIMEOUT,
    index_workspace,
    install_workspace,
)
from tests.acceptance.helpers.workspace import WRONG_ADD_EDITS

pytestmark = pytest.mark.acceptance

_FIXED_ADD = "    return a + b"


@pytest.fixture(scope="module")
def no_executor_run(oc_bin, tmp_path_factory):
    """One shared executor-less run (no provider configured anywhere)."""
    from tests.acceptance.helpers.workspace import make_workspace

    ws = make_workspace(tmp_path_factory.mktemp("no-exec"), "py_bugfix_basic")
    install_workspace(oc_bin, ws)
    index_workspace(oc_bin, ws)
    proc, summary = run_json(
        oc_bin,
        ["run", "Fix failing test in app.py", "--json"],
        cwd=ws.root,
        env=ws.env,
        timeout=WORKFLOW_TIMEOUT,
    )
    return ws, proc, summary


@pytest.fixture(scope="module")
def wrong_executor_run(oc_bin, tmp_path_factory):
    """One shared run whose deterministic executor applies a WRONG fix."""
    from tests.acceptance.helpers.workspace import make_workspace

    ws = make_workspace(tmp_path_factory.mktemp("wrong-exec"), "py_bugfix_basic")
    ws.write_stub_provider(WRONG_ADD_EDITS)
    install_workspace(oc_bin, ws)
    index_workspace(oc_bin, ws)
    proc, summary = run_json(
        oc_bin,
        ["run", "Fix failing test in app.py", "--json"],
        cwd=ws.root,
        env=ws.env,
        timeout=WORKFLOW_TIMEOUT,
    )
    return ws, proc, summary


@pytest.mark.smoke
def test_run_without_executor_reports_needs_executor(no_executor_run) -> None:
    """AC-009: `run` without an executor returns `needs_executor`, not `passed`."""
    _ws, _proc, summary = no_executor_run
    assert summary.get("status") == "needs_executor", (
        f"RUN_STATE_CONTRACT rule 4 (no silent downgrades): a missing executor is "
        f"needs_executor, got {summary.get('status')!r}"
    )
    assert summary["status"] not in {"passed", "completed"}
    assert summary.get("mutation_required") is True, summary


def test_run_without_executor_exits_5(no_executor_run) -> None:
    """AC-009: a workflow `run` ending needs_executor must exit with code 5."""
    _ws, proc, summary = no_executor_run
    assert summary.get("status") == "needs_executor"
    assert proc.returncode == 5, f"expected exit 5, got {proc.returncode}"


@pytest.mark.smoke
def test_run_with_correct_executor_mutates_and_verifies(oc_bin, stub_run) -> None:
    """AC-010: `run` with a correct executor mutates the file and passes verification."""
    ws = stub_run["ws"]
    proc = stub_run["run_proc"]
    summary = stub_run["summary"]

    assert proc.returncode == 0, proc.stderr[:500]
    # The mutation actually landed in the working tree.
    assert _FIXED_ADD in (ws.root / "app.py").read_text(encoding="utf-8")
    # Verification ran a REAL command and passed (evidence, not vibes).
    assert summary.get("verification_outcome") == "passed", summary
    assert summary.get("verified_by"), "a passed run must name its verification commands"
    assert any("pytest" in cmd for cmd in summary["verified_by"])
    assert summary.get("escalated") is False, summary
    assert summary.get("mutation_required") is True, summary


def test_run_success_uses_canonical_passed_state(stub_run) -> None:
    """AC-010: a fully verified run reports the canonical `passed` state."""
    assert stub_run["summary"].get("status") == "passed", stub_run["summary"].get("status")


@pytest.mark.smoke
def test_run_with_wrong_executor_never_reports_success(wrong_executor_run) -> None:
    """AC-011: `run` with a wrong executor must not report success."""
    _ws, _proc, summary = wrong_executor_run
    assert summary.get("status") not in {"passed", "completed"}, (
        f"RUN_STATE_CONTRACT rule 1 (no passed without evidence): verification failed "
        f"but run reported {summary.get('status')!r}"
    )
    assert summary.get("verification_outcome") == "failed", summary


def test_run_with_wrong_executor_exits_failed(wrong_executor_run) -> None:
    """AC-011: `run` with a wrong executor returns `failed` and a non-zero exit code."""
    _ws, proc, summary = wrong_executor_run
    assert summary.get("status") == "failed", summary.get("status")
    assert proc.returncode in (1, 8), f"expected exit 1 or 8, got {proc.returncode}"
