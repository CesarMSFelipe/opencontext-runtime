"""AC-017 / AC-018 / AC-019: memory — save/search/get, reuse reporting, compaction.

Contracts: MEMORY_CONTRACT.md, ACCEPTANCE_CONTRACT.md.
"""

from __future__ import annotations

import json

import pytest

from tests.acceptance.helpers.cli import run, run_json
from tests.acceptance.helpers.ops import find_run_dir, install_workspace

pytestmark = pytest.mark.acceptance


def test_memory_save_search_get_roundtrip(oc_bin, workspace) -> None:
    """AC-017: `memory save/search/get` works."""
    ws = workspace("memory_reuse_basic")
    install_workspace(oc_bin, ws)

    proc, receipt = run_json(
        oc_bin,
        [
            "memory",
            "v2",
            "save",
            "--title",
            "Fixed N+1 query in UserList",
            "--content",
            "Root cause: missing select_related on the user queryset.",
            "--type",
            "bugfix",
        ],
        cwd=ws.root,
        env=ws.env,
    )
    assert proc.returncode == 0, proc.stderr[:400]
    saved_id = receipt["receipt"]["id"]
    assert isinstance(saved_id, int)

    proc, results = run_json(
        oc_bin,
        ["memory", "v2", "search", "--query", "N+1 query UserList"],
        cwd=ws.root,
        env=ws.env,
    )
    assert proc.returncode == 0, proc.stderr[:400]
    assert any(r["id"] == saved_id for r in results), (
        f"saved observation {saved_id} not found by search: {results}"
    )

    proc, observation = run_json(
        oc_bin,
        ["memory", "v2", "get", "--id", str(saved_id)],
        cwd=ws.root,
        env=ws.env,
    )
    assert proc.returncode == 0, proc.stderr[:400]
    assert observation["id"] == saved_id
    assert observation["title"] == "Fixed N+1 query in UserList"
    assert "select_related" in observation["content"]
    assert observation["lifecycle_state"] == "active"


def test_second_run_reports_approved_memory_as_used(stub_run) -> None:
    """AC-018: a second run retrieves approved memory and reports it as used."""
    # A relevant memory existed BEFORE this run (saved in the stub_run fixture).
    assert stub_run["memory_receipt"]["receipt"]["id"]

    ws = stub_run["ws"]
    run_dir = find_run_dir(ws, stub_run["summary"]["run_id"])
    candidates = [run_dir / "run.json", run_dir / "state.json"]
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in candidates if p.is_file()]
    assert reports, f"no run report found in {run_dir}"
    memory_blocks = [r.get("memory") for r in reports if isinstance(r, dict) and r.get("memory")]
    assert memory_blocks, (
        "MEMORY_CONTRACT rule 4: every memory hit used by a run is recorded in the run report"
    )
    block = memory_blocks[0]
    assert block.get("used") is True
    assert block.get("hits"), "the retrieved memory must be listed with id/score/used_for"


def test_memory_compact_preserves_protected_memory(oc_bin, workspace) -> None:
    """AC-019: `memory compact` reduces old entries without deleting protected memory."""
    ws = workspace("memory_reuse_basic")
    install_workspace(oc_bin, ws)

    proc, receipt = run_json(
        oc_bin,
        [
            "memory",
            "v2",
            "save",
            "--title",
            "Protected architecture decision",
            "--content",
            "We keep the hexagonal core; adapters stay in the outer ring.",
            "--type",
            "decision",
        ],
        cwd=ws.root,
        env=ws.env,
    )
    assert proc.returncode == 0, proc.stderr[:400]
    saved_id = receipt["receipt"]["id"]
    pin = run(oc_bin, ["memory", "v2", "pin", "--id", str(saved_id)], cwd=ws.root, env=ws.env)
    assert pin.returncode == 0, pin.stderr[:400]

    compact = run(oc_bin, ["memory", "compact"], cwd=ws.root, env=ws.env)
    assert compact.returncode == 0, (
        f"MEMORY_CONTRACT command surface: `memory compact` must exist, "
        f"got exit {compact.returncode}: {compact.stderr[:300]}"
    )

    # The pinned decision must survive compaction.
    proc, observation = run_json(
        oc_bin, ["memory", "v2", "get", "--id", str(saved_id)], cwd=ws.root, env=ws.env
    )
    assert proc.returncode == 0
    assert observation["deleted_at"] is None
