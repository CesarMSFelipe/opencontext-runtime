"""AC-025 / AC-026: run report bundle completeness and resumability.

Contracts: RUN_STATE_CONTRACT.md (evidence + resume rules), SDD_CONTRACT.md
(run artifact layout), ACCEPTANCE_CONTRACT.md.
"""

from __future__ import annotations

import pytest

from tests.acceptance.helpers.cli import run_json
from tests.acceptance.helpers.ops import find_run_dir, read_json

pytestmark = pytest.mark.acceptance


def test_report_bundle_contains_all_evidence(stub_run) -> None:
    """AC-025: the report bundle contains manifest, commands, diffs, verification, deltas."""
    ws = stub_run["ws"]
    summary = stub_run["summary"]
    run_dir = find_run_dir(ws, summary["run_id"])
    artifacts = run_dir / "artifacts" / "oc-flow"

    # Run manifest (persisted state for the run).
    state = read_json(run_dir / "state.json")
    assert state["run_id"] == summary["run_id"]
    assert state["session_id"] == summary["session_id"]

    # Commands: the verification commands that were actually executed.
    assert state.get("verified_by"), "the report must name the executed verification commands"
    assert state.get("verification_outcome") == "passed"

    # Diff of the mutation.
    patch = artifacts / "patch.diff"
    assert patch.is_file() and patch.read_text(encoding="utf-8").strip(), (
        "the mutation diff must be persisted"
    )

    # Verification / inspection evidence.
    assert (artifacts / "inspection-report.json").is_file()
    assert (artifacts / "apply-receipts.json").is_file()

    # Memory delta and graph delta from consolidation.
    assert (artifacts / "consolidation" / "memory-delta.json").is_file()
    assert (artifacts / "consolidation" / "graph-delta.json").is_file()

    # Event log for the run.
    assert (run_dir / "events.json").is_file() or (run_dir / "events.jsonl").is_file()


def test_report_bundle_includes_run_manifest_and_gates(stub_run) -> None:
    """AC-025: the run directory persists run.json and gates.json (harness layout)."""
    ws = stub_run["ws"]
    run_dir = find_run_dir(ws, stub_run["summary"]["run_id"])
    assert (run_dir / "run.json").is_file(), f"run.json missing in {run_dir}"
    assert (run_dir / "gates.json").is_file(), f"gates.json missing in {run_dir}"


def test_resume_continues_without_duplicating_artifacts(oc_bin, stub_run) -> None:
    """AC-026: `run --resume` continues an interrupted run without duplicating artifacts."""
    ws = stub_run["ws"]
    summary = stub_run["summary"]
    resume_ref = f"{summary['session_id']}/{summary['run_id']}"

    sessions_dir = ws.root / ".opencontext" / "sessions"
    run_dirs_before = sorted(
        str(p) for p in sessions_dir.rglob("*") if p.is_dir() and p.parent.name == "runs"
    )

    proc, resumed = run_json(
        oc_bin,
        ["run", "--resume", resume_ref, "--json"],
        cwd=ws.root,
        env=ws.env,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    assert resumed.get("status") == "resumed", resumed
    # Resume attaches to the SAME run — same ids, no new run created.
    assert resumed.get("session_id") == summary["session_id"], resumed
    assert resumed.get("run_id") == summary["run_id"], resumed

    run_dirs_after = sorted(
        str(p) for p in sessions_dir.rglob("*") if p.is_dir() and p.parent.name == "runs"
    )
    assert run_dirs_after == run_dirs_before, (
        f"resume duplicated run artifacts: {set(run_dirs_after) - set(run_dirs_before)}"
    )
