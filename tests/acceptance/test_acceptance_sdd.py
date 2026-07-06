"""AC-014 / AC-015 / AC-016: SDD — connected artifacts, honest status, real gates.

Contracts: SDD_CONTRACT.md (artifact layout, status JSON, state machine),
ACCEPTANCE_CONTRACT.md.
"""

from __future__ import annotations

import json

import pytest

from tests.acceptance.helpers.cli import run, run_json
from tests.acceptance.helpers.ops import (
    WORKFLOW_TIMEOUT,
    index_workspace,
    install_workspace,
)

pytestmark = pytest.mark.acceptance

_CHANGE = "add-farewell-greeting"

#: Deterministic ApplyEdit set: adds farewell() to the sdd_feature_basic app.
_FAREWELL_EDITS = [
    {
        "path": "app.py",
        "operation": "replace_range",
        "start_line": 5,
        "end_line": 5,
        "content": (
            '    return "hello " + name\n\n\ndef farewell(name):\n    return "goodbye " + name'
        ),
        "reason": "add farewell(name) per the change spec",
        "requirement_refs": ["farewell returns a goodbye greeting"],
    }
]


def _write_planning_artifacts(change_root) -> None:
    """Author the connected planning artifacts the way an agent would."""
    (change_root / "proposal.md").write_text(
        "# Proposal: add-farewell-greeting\n\n- **Status:** approved\n\n"
        "## Intent\n\nUsers need a farewell message next to the greeting.\n\n"
        '## Scope\n\napp.py gains farewell(name) returning "goodbye <name>".\n',
        encoding="utf-8",
    )
    spec_dir = change_root / "specs" / "greeting"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(
        "# Spec: greeting farewell\n\n## ADDED Requirements\n\n"
        "### Requirement: farewell returns a goodbye greeting\n\n"
        'farewell(name) SHALL return "goodbye " + name.\n\n'
        "#### Scenario: basic farewell\n\n"
        '- WHEN farewell("bob") is called\n- THEN it returns "goodbye bob"\n',
        encoding="utf-8",
    )
    (change_root / "design.md").write_text(
        "# Design\n\nAdd farewell(name) beside greet(name) in app.py, "
        "mirroring the greet implementation.\n",
        encoding="utf-8",
    )
    (change_root / "tasks.md").write_text(
        "# Tasks\n\n- [ ] 1. Add farewell(name) to app.py\n- [ ] 2. Cover farewell with a test\n",
        encoding="utf-8",
    )


@pytest.fixture(scope="module")
def sdd_ws(oc_bin, tmp_path_factory):
    """sdd_feature_basic with `sdd init` + `sdd new <change>` already run."""
    from tests.acceptance.helpers.workspace import make_workspace

    ws = make_workspace(tmp_path_factory.mktemp("sdd"), "sdd_feature_basic")
    install_workspace(oc_bin, ws)
    proc = run(oc_bin, ["sdd", "init"], cwd=ws.root, env=ws.env)
    assert proc.returncode == 0, proc.stderr[:500]
    proc = run(oc_bin, ["sdd", "new", _CHANGE], cwd=ws.root, env=ws.env)
    assert proc.returncode == 0, proc.stderr[:500]
    return ws


def test_sdd_new_creates_cycle_and_initial_artifacts(sdd_ws) -> None:
    """AC-014: `sdd new` creates a cycle and its initial artifacts."""
    # Project-level SDD context from init.
    assert (sdd_ws.root / ".opencontext" / "sdd" / "context.json").is_file(), (
        "SDD_CONTRACT: sdd init must persist .opencontext/sdd/context.json"
    )
    # Per-change scaffold from new.
    change_root = sdd_ws.root / "openspec" / "changes" / _CHANGE
    assert change_root.is_dir(), "sdd new must scaffold openspec/changes/<change>/"
    artifacts = [p.name for p in change_root.iterdir()]
    assert artifacts, "the new change must contain at least one initial artifact"


def test_sdd_status_recognizes_the_scaffolded_proposal(oc_bin, sdd_ws) -> None:
    """AC-015: the artifact `sdd new` scaffolds is recognized by `sdd status`."""
    proc, status = run_json(
        oc_bin,
        ["sdd", "status", "--change", _CHANGE, "--json"],
        cwd=sdd_ws.root,
        env=sdd_ws.env,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    assert status["artifacts"]["proposal"] != "missing", (
        f"sdd new scaffolded an artifact that sdd status cannot see: {status['artifacts']}"
    )


def test_sdd_phases_consume_and_produce_connected_artifacts(oc_bin, sdd_ws) -> None:
    """AC-015: `sdd propose/spec/design/tasks` consume and produce connected artifacts."""
    change_root = sdd_ws.root / "openspec" / "changes" / _CHANGE
    _write_planning_artifacts(change_root)

    proc, status = run_json(
        oc_bin,
        ["sdd", "status", "--change", _CHANGE, "--json"],
        cwd=sdd_ws.root,
        env=sdd_ws.env,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    # The resolver consumes the whole artifact chain and reports its state.
    assert status["artifacts"]["proposal"] == "done", status["artifacts"]
    assert status["artifacts"]["specs"] == "done", status["artifacts"]
    assert status["artifacts"]["design"] == "done", status["artifacts"]
    # tasks.md has unchecked items => "partial" by contract.
    assert status["artifacts"]["tasks"] == "partial", status["artifacts"]
    assert status["nextRecommended"] == "apply", status
    assert isinstance(status["blockedReasons"], list)

    # Dependency enforcement: verify may not run before apply completed.
    proc, verify = run_json(
        oc_bin,
        ["sdd", "verify", "--change", _CHANGE],
        cwd=sdd_ws.root,
        env=sdd_ws.env,
    )
    assert verify.get("status") == "blocked", (
        f"SDD_CONTRACT state machine: verify before apply must block, got {verify}"
    )
    assert verify.get("next_recommended") == "apply", verify


def test_sdd_harness_run_executes_real_gates(oc_bin, workspace) -> None:
    """AC-016: `sdd apply/verify` execute real gates (via the SDD harness run)."""
    ws = workspace("sdd_feature_basic")
    ws.write_stub_provider(_FAREWELL_EDITS)
    install_workspace(oc_bin, ws)
    index_workspace(oc_bin, ws)

    proc, summary = run_json(
        oc_bin,
        [
            "run",
            "Add a farewell(name) function returning a goodbye greeting",
            "--workflow",
            "sdd",
            "--json",
        ],
        cwd=ws.root,
        env=ws.env,
        timeout=WORKFLOW_TIMEOUT,
    )
    assert proc.returncode == 0, proc.stderr[:600]
    assert summary.get("workflow") == "sdd", summary
    assert summary.get("status") not in {"failed", "blocked", "cancelled"}, summary

    # Real gate evidence: the harness bundle under .opencontext/runs/<run_id>/
    # (SDD_CONTRACT artifact layout) with executed, non-empty gate results.
    run_id = summary["run_id"]
    run_dir = ws.root / ".opencontext" / "runs" / run_id
    assert run_dir.is_dir(), f"SDD harness bundle missing at {run_dir}"
    assert (run_dir / "run.json").is_file(), "SDD run must persist run.json"
    gates_file = run_dir / "gates.json"
    assert gates_file.is_file(), "SDD run must persist gates.json"
    gates = json.loads(gates_file.read_text(encoding="utf-8"))["gates"]
    assert gates, "gates.json must record executed gates"
    for gate in gates:
        assert gate.get("id") and gate.get("phase") and gate.get("status"), gate
    assert any(g["status"] == "passed" for g in gates), f"no gate passed: {gates}"
    assert (run_dir / "receipts" / "receipts.jsonl").is_file(), "SDD apply must persist receipts"

    # The AER session manifest for the same run also exists.
    session_manifests = list(
        (ws.root / ".opencontext" / "sessions").glob(f"*/runs/{run_id}/manifest.json")
    )
    assert session_manifests, "SDD run must persist its session run manifest"

    # The apply gate did real work: the mutation landed.
    assert "def farewell(name)" in (ws.root / "app.py").read_text(encoding="utf-8")
