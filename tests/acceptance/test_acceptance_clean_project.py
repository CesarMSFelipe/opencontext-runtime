"""AC-031: executions leave no artifacts in the project.

Contracts: PRODUCT_CONTRACT.md §Storage modes (execution state stays out of
the project), RUN_STATE_CONTRACT.md (evidence still persisted — globally),
ACCEPTANCE_CONTRACT.md.

Black-box: after install + index + a full `run` with the test-stub executor
in user mode (the default), a before/after snapshot of the project tree may
differ ONLY by the intended mutation. All execution state (sessions, runs,
checkpoints, receipts) must land in the XDG project state dir instead.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

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


def _snapshot(root: Path) -> dict[str, str]:
    """Relative path → content hash for every file under *root* (no exclusions)."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_run_adds_no_files_to_the_project_tree(oc_bin, workspace) -> None:
    """AC-031: executions leave no artifacts in the project.

    The snapshot diff between "after install+index" and "after run" must show
    the intended mutation only: no new files, no deleted files, no other
    content changes (PRODUCT_CONTRACT §Storage modes).
    """
    ws = workspace("py_bugfix_basic")
    ws.write_stub_provider(CORRECT_ADD_EDITS)
    install_workspace(oc_bin, ws)
    index_workspace(oc_bin, ws)

    before = _snapshot(ws.root)

    proc, summary = run_json(
        oc_bin,
        ["run", "Fix failing test in app.py", "--json"],
        cwd=ws.root,
        env=ws.env,
        timeout=WORKFLOW_TIMEOUT,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    assert summary.get("status") == "passed", summary.get("status")

    after = _snapshot(ws.root)

    added = sorted(set(after) - set(before))
    assert added == [], (
        f"PRODUCT_CONTRACT storage modes: a user-mode run must add NO files to the "
        f"project tree (execution state belongs in the XDG project dir), but added: {added}"
    )
    removed = sorted(set(before) - set(after))
    assert removed == [], (
        f"PRODUCT_CONTRACT storage modes: the run must not delete project files: {removed}"
    )
    changed = sorted(rel for rel in before if rel in after and after[rel] != before[rel])
    assert changed == ["app.py"], (
        f"PRODUCT_CONTRACT storage modes: only the intended mutation (app.py) may change "
        f"in the project tree, got: {changed}"
    )


def test_run_evidence_is_persisted_outside_the_project(oc_bin, workspace) -> None:
    """AC-031 companion: the evidence still exists — in the XDG state dir.

    A clean project must not mean lost evidence (RUN_STATE_CONTRACT): the run
    bundle is persisted under the isolated $XDG_STATE_HOME, outside the root.
    """
    ws = workspace("py_bugfix_basic")
    ws.write_stub_provider(CORRECT_ADD_EDITS)
    install_workspace(oc_bin, ws)
    index_workspace(oc_bin, ws)

    proc, summary = run_json(
        oc_bin,
        ["run", "Fix failing test in app.py", "--json"],
        cwd=ws.root,
        env=ws.env,
        timeout=WORKFLOW_TIMEOUT,
    )
    assert proc.returncode == 0, proc.stderr[:500]

    run_dir = find_run_dir(ws, summary["run_id"]).resolve()
    root = ws.root.resolve()
    assert root != run_dir and root not in run_dir.parents, (
        f"RUN_STATE_CONTRACT: the user-mode run bundle must live outside the project "
        f"root, got {run_dir}"
    )
    xdg_state = Path(ws.env["XDG_STATE_HOME"]).resolve()
    assert xdg_state in run_dir.parents, (
        f"RUN_STATE_CONTRACT: the run bundle must live under the isolated XDG state "
        f"dir {xdg_state}, got {run_dir}"
    )
