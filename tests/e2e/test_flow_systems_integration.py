"""Every OpenContext subsystem engages during a real, offline flow run.

Permanent regression guard ("asegura todos los sistemas"): a mutating OC Flow
run plus an SDD strict-TDD RED->GREEN run are driven end-to-end OFFLINE via the
deterministic ``test_stub`` gateway (no provider, no network), and EACH mapped
subsystem is asserted against its concrete on-disk evidence. A regression in any
single subsystem fails its own dedicated assertion, naming the exact system that
broke.

Two runs are used because no single run exercises both the read-path context
assembly (KG grounding + memory recall + compression evaluation) and the SDD
strict-TDD RED/GREEN harness gate:

- ``test_ocflow_run_engages_all_read_and_write_subsystems`` — PATH A: an indexed,
  memory-seeded, compression-enabled OC Flow mutation. Covers KG grounding,
  memory recall, memory write-back/consolidation, compression, context
  receipt/envelope, graph delta, cost/token tracking, apply-receipts+checksums,
  task contract, local inspection, patch/diff, run state honesty gate, decision
  receipts, events ledger, init/capabilities binding, checkpoint/rollback safety.
- ``test_sdd_strict_tdd_run_engages_harness_gates`` — PATH B: an SDD strict-TDD
  run with a correct fix. Covers the harness gates + TDD GREEN gate, the
  consolidated harness report, workflow-selection receipt, and run-index
  registration.
- ``test_sdd_strict_tdd_wrong_fix_fails_green_gate`` — PATH B negative branch: a
  wrong fix (``return a * b``) drives the GREEN gate to ``failed``, proving the
  gate is real and not a rubber stamp.

The tests invoke the OpenContext CLI directly (subprocess ``python -m
opencontext_cli.main``) and the in-process harness API; no host binaries are
required, so this runs in normal CI ``pytest`` (no ``real_host`` marker).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from opencontext_core.harness.runner import HarnessRunner

_REPO = Path(__file__).resolve().parents[2]
_GOLDEN = _REPO / "tests" / "golden" / "oc_flow_bugfix_python"
_PKGS = [
    _REPO / "packages" / p
    for p in ("opencontext_core", "opencontext_cli", "opencontext_memory", "opencontext_sdd")
]

# A multi-symbol buggy module: add() returns a-b (the bug), and total() calls add().
_BUGGY_MODULE = (
    "def add(a, b):\n"
    "    return a - b\n"
    "\n"
    "\n"
    "def total(xs):\n"
    "    acc = 0\n"
    "    for x in xs:\n"
    "        acc = add(acc, x)\n"
    "    return acc\n"
)
_FIXED_LINE = "    return a + b"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX12 = re.compile(r"^[0-9a-f]{12}$")
_KG_SCORE = re.compile(r"^kg:score=\d\.\d{2}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_CHECKPOINT_ID = re.compile(r"^\d{8}T\d{6}_")


# --------------------------------------------------------------------------- CLI helpers
def _env(home: Path) -> dict[str, str]:
    """An isolated HOME + local storage so ~/.opencontext daemon pollution can't flake."""
    entries = [
        str(Path(r).resolve()) for r in os.environ.get("PYTHONPATH", "").split(os.pathsep) if r
    ]
    for pkg in _PKGS:
        if str(pkg) not in entries:
            entries.append(str(pkg))
    return {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PYTHONPATH": os.pathsep.join(entries),
        "OPENCONTEXT_STORAGE_MODE": "local",
        # The mutating run rewrites a source file and then (SDD path) re-imports it
        # in a nested pytest within the same second; disable bytecode caching so no
        # stale ``.pyc`` from the pre-mutation source is reused (mtime granularity).
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _oc(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # sys.executable (not bare "python") so the subprocess uses the same interpreter
    # as the test runner on every platform, incl. Windows where "python" may be a
    # Store shim or absent.
    return subprocess.run(
        [sys.executable, "-m", "opencontext_cli.main", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ======================================================================= PATH A: OC Flow
def test_ocflow_run_engages_all_read_and_write_subsystems(tmp_path: Path) -> None:
    """A mutating OC Flow run engages the full read+write subsystem set, offline.

    Seeds a KG index and a memory observation, then drives a ``test_stub`` mutation
    so every subsystem writes real evidence. Each subsystem below gets its OWN
    assert message so a regression points at the exact system that broke.
    """
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()

    # Copy the shipped test_stub fixture (buggy_add + failing test + provider_stub +
    # opencontext.yaml declaring provider: test_stub), then widen it to a multi-symbol
    # module so graph delta / reindex has a real target.
    shutil.copytree(_GOLDEN, proj, dirs_exist_ok=True)
    (proj / "buggy_add.py").write_text(_BUGGY_MODULE, encoding="utf-8")

    # Enable memory write-back + compression evaluation on top of the fixture config.
    cfg = (proj / "opencontext.yaml").read_text(encoding="utf-8")
    cfg += (
        "\nmemory:\n"
        "  enabled: true\n"
        "  harvest_after_run: true\n"
        "context:\n"
        "  compression:\n"
        "    enabled: true\n"
    )
    (proj / "opencontext.yaml").write_text(cfg, encoding="utf-8")

    env = _env(home)

    # PREP: init, index (KG grounding), memory v2 save (recall seed).
    assert _oc(["init"], proj, env).returncode == 0
    idx = _oc(["index", "."], proj, env)
    assert idx.returncode == 0, idx.stderr
    graph_db = proj / ".storage" / "opencontext" / "context_graph.db"
    assert graph_db.is_file(), "index . did not build the KG (context_graph.db missing)"

    saved = _oc(
        [
            "memory",
            "v2",
            "save",
            "--title",
            "Add rule",
            "--content",
            "buggy_add add function must return the sum of arguments a plus b",
            "--type",
            "decision",
        ],
        proj,
        env,
    )
    assert saved.returncode == 0, saved.stderr

    # RUN: a mutating OC Flow run through the test_stub gateway (offline).
    run = _oc(
        [
            "run",
            "fix failing test in buggy_add add returns sum",
            "--workflow",
            "oc-flow",
            "--json",
            "--yes",
        ],
        proj,
        env,
    )
    assert run.returncode == 0, run.stderr
    summary = json.loads(run.stdout[run.stdout.index("{") :])
    run_id = summary["run_id"]

    # Locate the run artifact dir under .opencontext/sessions/*/runs/*/artifacts/oc-flow.
    receipts = list((proj / ".opencontext").rglob("artifacts/oc-flow/context-receipt.json"))
    assert receipts, "no OC Flow run artifacts produced (context-receipt.json missing)"
    artifacts = receipts[0].parent
    run_dir = artifacts.parent.parent  # runs/<run_id>

    context_receipt = _load_json(artifacts / "context-receipt.json")
    context_envelope = _load_json(artifacts / "context-envelope.json")
    state = _load_json(run_dir / "state.json")

    # --- The buggy file was actually fixed (the whole point of a mutating run). ------
    assert (
        (proj / "buggy_add.py")
        .read_text(encoding="utf-8")
        .startswith("def add(a, b):\n    return a + b\n")
    ), "mutation did not fix buggy_add.add (offline test_stub apply failed)"

    # --- Subsystem: Knowledge graph grounding (KG-first envelope seeding) -------------
    kg_reasons = [
        i.get("why_included", "")
        for i in context_receipt.get("items", [])
        if _KG_SCORE.match(str(i.get("why_included", "")))
    ]
    assert kg_reasons, (
        "SUBSYSTEM 'Knowledge graph grounding': no context item has "
        "why_included matching 'kg:score=D.DD' (index . did not seed the envelope)"
    )

    # --- Subsystem: Memory recall (observations fold-in) -----------------------------
    receipt_reasons = [str(i.get("why_included", "")) for i in context_receipt.get("items", [])]
    assert "memory:observation" in receipt_reasons, (
        "SUBSYSTEM 'Memory recall': no context item has why_included == "
        "'memory:observation' (the CLI-saved observation was not recalled)"
    )
    assert "memory:observation" in json.dumps(context_envelope), (
        "SUBSYSTEM 'Memory recall': envelope does not carry the recalled observation"
    )

    # --- Subsystem: Memory write-back / consolidation (harvester sole-writer) ---------
    memory_delta = _load_json(artifacts / "consolidation" / "memory-delta.json")
    harvest = memory_delta.get("harvest", {})
    assert harvest.get("persisted") is True, (
        "SUBSYSTEM 'Memory write-back': harvest.persisted is not True "
        f"(got {harvest.get('persisted')!r}; harvest_after_run not honored)"
    )
    assert harvest.get("origin") == "agent", (
        f"SUBSYSTEM 'Memory write-back': harvest.origin != 'agent' (got {harvest.get('origin')!r})"
    )
    assert re.match(r"^(harness|harvester-legacy)$", str(harvest.get("via", ""))), (
        "SUBSYSTEM 'Memory write-back': harvest.via not one of harness/harvester-legacy "
        f"(got {harvest.get('via')!r})"
    )
    assert harvest.get("run_id") == run_id, (
        "SUBSYSTEM 'Memory write-back': harvest.run_id does not match the run "
        f"({harvest.get('run_id')!r} != {run_id!r})"
    )

    # --- Subsystem: Compression engine (evaluated even when not applied) --------------
    compression = context_receipt.get("compression", {})
    assert compression.get("enabled") is True, (
        "SUBSYSTEM 'Compression engine': compression.enabled is not True "
        "(context.compression.enabled not honored)"
    )
    assert compression.get("applied") in (True, False), (
        "SUBSYSTEM 'Compression engine': compression.applied not evaluated "
        f"(got {compression.get('applied')!r})"
    )
    assert isinstance(compression.get("ratio"), (int, float)), (
        "SUBSYSTEM 'Compression engine': compression.ratio is not numeric "
        f"(got {compression.get('ratio')!r})"
    )

    # --- Subsystem: Context receipt / envelope (ranking + budget provenance) ---------
    ranking_hash = context_envelope.get("ranking_hash", "")
    assert _HEX12.match(str(ranking_hash)), (
        "SUBSYSTEM 'Context receipt/envelope': ranking_hash is not 12 hex chars "
        f"(got {ranking_hash!r})"
    )
    assert context_receipt.get("ranking_hash") == ranking_hash, (
        "SUBSYSTEM 'Context receipt/envelope': receipt/envelope ranking_hash mismatch"
    )
    assert context_envelope.get("budget_available") == 4500, (
        "SUBSYSTEM 'Context receipt/envelope': budget_available != 4500 "
        f"(got {context_envelope.get('budget_available')!r})"
    )
    assert context_envelope.get("budget_used") == context_envelope.get("token_estimate"), (
        "SUBSYSTEM 'Context receipt/envelope': budget_used != token_estimate"
    )
    assert _UUID.match(str(context_envelope.get("receipt_id", ""))), (
        "SUBSYSTEM 'Context receipt/envelope': receipt_id is not a UUID "
        f"(got {context_envelope.get('receipt_id')!r})"
    )
    receipt_budget = context_receipt.get("budget", {})
    assert receipt_budget.get("available") == 4500, (
        "SUBSYSTEM 'Context receipt/envelope': receipt budget.available != 4500"
    )

    # --- Subsystem: Graph delta / mid-flow reindex -----------------------------------
    graph_delta = _load_json(artifacts / "consolidation" / "graph-delta.json")
    assert graph_delta.get("reindexed_files") == state.get("changed_files"), (
        "SUBSYSTEM 'Graph delta / reindex': reindexed_files != the mutated files "
        f"({graph_delta.get('reindexed_files')!r} != {state.get('changed_files')!r})"
    )
    assert graph_delta.get("reindexed_files"), (
        "SUBSYSTEM 'Graph delta / reindex': reindexed_files is empty (no reindex scheduled)"
    )

    # --- Subsystem: Cost / token tracking --------------------------------------------
    cost_report = _load_json(artifacts / "consolidation" / "cost-report.json")
    assert cost_report.get("changed_files") == 1, (
        "SUBSYSTEM 'Cost/token tracking': cost-report.changed_files != 1 "
        f"(got {cost_report.get('changed_files')!r})"
    )
    assert isinstance(state.get("total_tokens"), int) and state["total_tokens"] > 0, (
        "SUBSYSTEM 'Cost/token tracking': state.total_tokens is not a positive int "
        f"(got {state.get('total_tokens')!r})"
    )

    # --- Subsystem: Apply receipts WITH before/after checksums (needs a mutation) -----
    apply_receipts = _load_json(artifacts / "apply-receipts.json")
    checkpoint_id = apply_receipts.get("checkpoint_id", "")
    assert _CHECKPOINT_ID.match(str(checkpoint_id)), (
        "SUBSYSTEM 'Apply receipts / checkpoint': checkpoint_id not a timestamped id "
        f"(got {checkpoint_id!r})"
    )
    recs = apply_receipts.get("receipts", [])
    assert recs, "SUBSYSTEM 'Apply receipts': receipts is empty after a real mutation"
    rec = recs[0]
    assert _HEX64.match(str(rec.get("checksum_before", ""))), (
        "SUBSYSTEM 'Apply receipts': checksum_before is not 64 hex chars "
        f"(got {rec.get('checksum_before')!r})"
    )
    assert _HEX64.match(str(rec.get("checksum_after", ""))), (
        "SUBSYSTEM 'Apply receipts': checksum_after is not 64 hex chars "
        f"(got {rec.get('checksum_after')!r})"
    )
    assert rec["checksum_before"] != rec["checksum_after"], (
        "SUBSYSTEM 'Apply receipts': checksum_before == checksum_after (no bytes changed)"
    )
    assert rec.get("path") == "buggy_add.py", (
        f"SUBSYSTEM 'Apply receipts': receipt path != buggy_add.py (got {rec.get('path')!r})"
    )
    assert rec.get("changed") is True, "SUBSYSTEM 'Apply receipts': receipt.changed is not True"

    # --- Subsystem: Checkpoint / rollback capability (safety net) ---------------------
    # A real timestamped checkpoint_id (asserted above) proves node_mutate created a
    # rollback checkpoint over the changed paths before applying the edit.
    assert checkpoint_id and checkpoint_id != "empty", (
        "SUBSYSTEM 'Checkpoint/rollback': no real checkpoint captured before the mutation"
    )

    # --- Subsystem: Task contract (frozen plan) --------------------------------------
    task_contract = _load_json(artifacts / "task-contract.json")
    assert task_contract.get("acceptance_criteria"), (
        "SUBSYSTEM 'Task contract': acceptance_criteria is empty"
    )
    assert task_contract.get("verification_plan"), (
        "SUBSYSTEM 'Task contract': verification_plan is empty"
    )
    assert task_contract.get("scope"), "SUBSYSTEM 'Task contract': scope is empty"

    # --- Subsystem: Local inspection report (zero-LLM gates) --------------------------
    inspection = _load_json(artifacts / "inspection-report.json")
    assert inspection.get("verification_outcome") == "passed", (
        "SUBSYSTEM 'Local inspection': verification_outcome != 'passed' "
        f"(got {inspection.get('verification_outcome')!r})"
    )
    assert state.get("verification_outcome") == "passed", (
        "SUBSYSTEM 'Local inspection': state.verification_outcome != 'passed'"
    )

    # --- Subsystem: Patch / unified diff ---------------------------------------------
    patch = (artifacts / "patch.diff").read_text(encoding="utf-8")
    assert "--- a/buggy_add.py" in patch and "+++ b/buggy_add.py" in patch, (
        "SUBSYSTEM 'Patch/diff': unified diff headers for buggy_add.py missing"
    )
    assert "+" + _FIXED_LINE in patch, (
        "SUBSYSTEM 'Patch/diff': the '+    return a + b' hunk line is missing"
    )
    assert "# no edits proposed" not in patch, (
        "SUBSYSTEM 'Patch/diff': honest no-op sentinel present on a real mutation"
    )

    # --- Subsystem: Run state + completion honesty gate ------------------------------
    assert state.get("status") == "completed", (
        f"SUBSYSTEM 'Run state honesty': status != 'completed' (got {state.get('status')!r})"
    )
    assert state.get("mutation_required") is True, (
        "SUBSYSTEM 'Run state honesty': mutation_required is not True"
    )
    assert state.get("completion_reason") == "mutation verified", (
        "SUBSYSTEM 'Run state honesty': completion_reason != 'mutation verified' "
        f"(got {state.get('completion_reason')!r})"
    )
    assert state.get("changed_files") == ["buggy_add.py"], (
        "SUBSYSTEM 'Run state honesty': changed_files != ['buggy_add.py'] "
        f"(got {state.get('changed_files')!r})"
    )

    # --- Subsystem: Decision receipts (Runtime Brain / selection points) -------------
    decisions = _load_json(run_dir / "decisions.json").get("decisions", [])
    kinds = {d.get("kind") for d in decisions}
    expected_kinds = {
        "workflow",
        "context_strategy",
        "provider",
        "execution_profile",
        "retry_policy",
        "next_node",
        "memory_promotion",
        "confidence_report",
    }
    missing = expected_kinds - kinds
    assert not missing, (
        f"SUBSYSTEM 'Decision receipts': missing decision kinds {sorted(missing)} "
        f"(present: {sorted(kinds)})"
    )

    # --- Subsystem: Events ledger ----------------------------------------------------
    events = _load_json(run_dir / "events.json").get("events", [])
    event_types = {e.get("type") for e in events}
    for required in ("workflow.selected", "node.started", "node.completed", "decision.recorded"):
        assert required in event_types, (
            f"SUBSYSTEM 'Events ledger': event type {required!r} missing "
            f"(present: {sorted(event_types)})"
        )
    assert all(e.get("family") == "workflow" for e in events), (
        "SUBSYSTEM 'Events ledger': not all events carry family == 'workflow'"
    )

    # --- Subsystem: Init record + capabilities / policy binding ----------------------
    init_record = _load_json(artifacts / "init.json")
    assert init_record.get("workflow") == "oc-flow", (
        "SUBSYSTEM 'Init/capabilities': workflow != 'oc-flow' "
        f"(got {init_record.get('workflow')!r})"
    )
    assert init_record.get("policy_mode") == "default", (
        f"SUBSYSTEM 'Init/capabilities': policy_mode != 'default' "
        f"(got {init_record.get('policy_mode')!r})"
    )
    assert init_record.get("capabilities_available") is True, (
        "SUBSYSTEM 'Init/capabilities': capabilities_available is not True"
    )

    # --- Subsystem: Workflow selection receipt (oc-flow tree) ------------------------
    workflow_selection = _load_json(artifacts / "workflow-selection.json")
    assert workflow_selection.get("workflow") == "oc-flow", (
        "SUBSYSTEM 'Workflow selection': workflow-selection.json workflow != 'oc-flow'"
    )
    assert "task_type=test" in summary.get("selection_reason", ""), (
        "SUBSYSTEM 'Workflow selection': --json selection_reason missing 'task_type=test' "
        f"(got {summary.get('selection_reason')!r})"
    )


# ======================================================================= PATH B: SDD strict TDD
_SDD_BUGGY = "def add(a, b):\n    return a - b\n"
_SDD_TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
_SDD_CONFIG = (
    "version: 1\nprovider: test_stub\nedits_file: edits.json\nharness:\n  tdd_mode: strict\n"
)


def _sdd_edit(content: str) -> str:
    return json.dumps(
        [
            {
                "path": "calc.py",
                "operation": "replace_range",
                "start_line": 2,
                "end_line": 2,
                "content": content,
                "reason": "fix",
                "requirement_refs": ["add returns the sum"],
            }
        ]
    )


def _sdd_project(root: Path, edit_content: str) -> Path:
    (root / "calc.py").write_text(_SDD_BUGGY, encoding="utf-8")
    (root / "test_calc.py").write_text(_SDD_TEST, encoding="utf-8")
    (root / "edits.json").write_text(_sdd_edit(edit_content), encoding="utf-8")
    (root / "opencontext.yaml").write_text(_SDD_CONFIG, encoding="utf-8")
    return root


def _tests_pass_gate(result: Any) -> Any:
    return next((g for g in result.gates if g.id == "tests_pass"), None)


def _sdd_run_dir(root: Path) -> Path:
    return next(p for p in (root / ".opencontext" / "runs").iterdir() if p.is_dir())


def test_sdd_strict_tdd_run_engages_harness_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An SDD strict-TDD run engages the harness gates + GREEN TDD gate, offline.

    Covers: harness gates + TDD RED/GREEN, consolidated harness report, workflow
    selection receipt, and run-index registration. The harness conftest pins
    OPENCONTEXT_TDD_MODE=off for determinism, so strict must be re-set explicitly
    or the GREEN gate reports 'inactive'.
    """
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    # The GREEN gate re-imports calc.py in a nested pytest right after the mutation
    # rewrote it; disable bytecode caching so no stale pre-mutation ``.pyc`` is reused.
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    root = _sdd_project(tmp_path, _FIXED_LINE)

    result = HarnessRunner(root=root).run("sdd", "fix failing test: add must return the sum")

    # test_stub mutated the file offline.
    assert (root / "calc.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n", (
        "SUBSYSTEM 'Harness apply (SDD)': test_stub did not mutate calc.py offline"
    )

    # --- Subsystem: Harness gates + TDD RED/GREEN (GREEN branch) ----------------------
    gate = _tests_pass_gate(result)
    assert gate is not None and gate.status == "passed", (
        f"SUBSYSTEM 'Harness TDD gate': tests_pass gate not passed (got {gate})"
    )
    assert "inactive" not in (gate.message or "").lower(), (
        "SUBSYSTEM 'Harness TDD gate': GREEN gate reported 'inactive' (strict TDD mode not honored)"
    )
    assert "green confirmed" in (gate.message or "").lower(), (
        f"SUBSYSTEM 'Harness TDD gate': message missing 'GREEN confirmed' (got {gate.message!r})"
    )

    run_dir = _sdd_run_dir(root)

    # gates.json on disk mirrors the passed GREEN gate.
    gates_on_disk = _load_json(run_dir / "gates.json").get("gates", [])
    disk_tp = next((g for g in gates_on_disk if g.get("id") == "tests_pass"), None)
    assert disk_tp and disk_tp.get("status") == "passed", (
        "SUBSYSTEM 'Harness TDD gate': gates.json tests_pass status != 'passed'"
    )

    # --- Subsystem: Harness consolidated report --------------------------------------
    report = _load_json(run_dir / "harness-report.json")
    assert report.get("status"), "SUBSYSTEM 'Harness report': harness-report.json has no status"
    assert report.get("gates", {}).get("by_status", {}).get("passed", 0) >= 1, (
        "SUBSYSTEM 'Harness report': gates.by_status.passed < 1"
    )

    # --- Subsystem: Harness compliance matrix (conditional) --------------------------
    # compliance-matrix.json is written ONLY when a verify phase emits a
    # ComplianceMatrix gate carrying matrix metadata; a bare strict-TDD run does not,
    # so assert shape only when present rather than faking its existence.
    compliance = run_dir / "compliance-matrix.json"
    if compliance.is_file():
        matrix = _load_json(compliance)
        assert matrix, "SUBSYSTEM 'Harness compliance matrix': compliance-matrix.json is empty"

    # --- Subsystem: Workflow selection receipt (sdd tree) ----------------------------
    selection = _load_json(run_dir / "workflow-selection.json")
    assert selection.get("resolved") == "sdd", (
        "SUBSYSTEM 'Workflow selection (SDD)': resolved != 'sdd' "
        f"(got {selection.get('resolved')!r})"
    )

    # --- Subsystem: Run index registration -------------------------------------------
    index_path = root / ".opencontext" / "runs" / "index.json"
    assert index_path.is_file(), "SUBSYSTEM 'Run index': runs/index.json missing"
    assert result.run_id in index_path.read_text(encoding="utf-8"), (
        f"SUBSYSTEM 'Run index': run_id {result.run_id!r} not registered in index.json"
    )


def test_sdd_strict_tdd_wrong_fix_fails_green_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong fix drives the GREEN gate to 'failed' — the gate is not a rubber stamp."""
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    root = _sdd_project(tmp_path, "    return a * b")  # 2*3=6 != 5

    result = HarnessRunner(root=root).run("sdd", "fix failing test: add must return the sum")

    gate = _tests_pass_gate(result)
    assert gate is not None and gate.status == "failed", (
        f"SUBSYSTEM 'Harness TDD gate (negative)': wrong fix did not fail GREEN (got {gate})"
    )

    run_dir = _sdd_run_dir(root)
    report = _load_json(run_dir / "harness-report.json")
    assert report.get("gates", {}).get("by_status", {}).get("failed", 0) >= 1, (
        "SUBSYSTEM 'Harness report (negative)': harness-report shows no failed gate"
    )
