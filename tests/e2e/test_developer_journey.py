"""E2E DoD developer journey + the hard ``e2e-dod`` acceptance gate (B10 / AVH-010 / AVH-017).

Drives the audit Definition-of-Done sequence end-to-end on the golden bugfix fixture:

    install --yes -> doctor --strict -> index -> run "Fix failing test" --workflow auto
    -> pytest <golden> -> release acceptance

The ``run`` step is driven through the REAL CLI as a subprocess
(``python -m opencontext_cli.main run "Fix failing test" --workflow auto --json``):
the copied fixture ships an ``opencontext.yaml`` declaring ``provider: test_stub`` +
``edits_file: provider_stub.json``, so the live CLI resolves a deterministic
``TestStubGateway``-backed executor ITSELF (PROD-002 / B2) and patches the seeded bug
credential-free. This is the honest DoD proof — the full provider -> validate ->
policy -> checkpoint -> apply -> receipt -> inspection pipeline runs over the genuine
product surface; only the model is a deterministic stand-in. Nothing is injected
in-process, so the DoD measures the real ``opencontext run`` command end to end.

A proven sequence writes the DoD proof artifact; the mandatory ``e2e-dod`` gate then
reads ``MET``. An UNPROVEN sequence FAILS the gate in release mode (hard 1.0 gate) and
is honestly ``NOT_MEASURED`` in dev mode.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from opencontext_core.context.planning.workflow_selector import select_workflow
from opencontext_core.evaluation.models import GateStatus
from opencontext_core.models.llm import LLMResponse
from opencontext_core.oc_flow.cli import run_oc_flow_cli
from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor
from opencontext_core.oc_flow.runner import OCFlowRunner
from opencontext_core.operating_model.release_gate import (
    E2E_DOD_GATE,
    FUNCTIONAL_BEHAVIOURS,
    GOVERNANCE_GATES,
    AcceptanceEvaluator,
    read_dod_proof,
    read_release_evidence,
    write_dod_proof,
    write_release_evidence,
)

#: A clearly broad/high-risk task the shared selector must route to SDD (B5).
_FORMAL_TASK = (
    "Design and implement a new public authentication API: add OAuth2 login, migrate "
    "the user database schema, run a security review, and define a staged rollout plan."
)

#: The fixed source the golden bugfix run must produce in ``buggy_add.py``.
_FIXED_SRC = "def add(a, b):\n    return a + b\n"


class _StubGateway:
    """Deterministic provider stub for the in-process run step (no live LLM)."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[object] = []

    def generate(self, request: object) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(
            content=self._content, provider="mock", model="e2e-stub",
            input_tokens=1, output_tokens=1,
        )


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TRACEABILITY_MATRIX = (
    _PROJECT_ROOT
    / "docs"
    / "OpenContext_Complete_Plans_and_Architecture_Book"
    / "54-requirement-to-pr-traceability-matrix.md"
)
_MATRIX_STATUS_LEGEND = {"MET", "PROPOSED", "DEFERRED", "REJECTED"}


def _cli(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "opencontext_cli.main", *argv],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=240, check=False,
    )


def _met(detail: str) -> list[str]:
    """An evidence value the acceptance evaluator parses as a MET with a detail."""
    return ["met", detail]


def _traceability_has_no_orphans() -> tuple[bool, str]:
    """Every requirement row in the 54-matrix carries a Status + an assigned PR (D)."""
    if not _TRACEABILITY_MATRIX.is_file():
        return False, "traceability matrix not found"
    orphans = 0
    rows = 0
    for raw in _TRACEABILITY_MATRIX.read_text(encoding="utf-8").splitlines():
        # An escaped pipe (``\|``) inside a cell is content, not a column separator.
        line = raw.strip().replace("\\|", "/")
        if not (line.startswith("| **") and "**" in line):
            continue  # only requirement rows (bolded id), not headers/separators
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 7:
            continue
        rows += 1
        pr, status = cols[2], cols[6]
        if not pr or status not in _MATRIX_STATUS_LEGEND:
            orphans += 1
    if rows == 0:
        return False, "no requirement rows parsed"
    if orphans:
        return False, f"{orphans}/{rows} requirement rows orphaned"
    return True, f"{rows} requirement rows; every one carries a Status + assigned PR"


def _collect_functional_governance(
    work: Path, steps: list[dict[str, object]], summary: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    """Derive the 15 B + 3 D gate outcomes from the REAL journey (VDM-007).

    Best-effort + honest: a behaviour is recorded MET only on a genuine observation; a
    dimension the journey could not exercise here is simply omitted so its gate stays
    NOT_MEASURED — never a fabricated pass (build-rule #1).
    """
    by_step = {str(s.get("step")): s for s in steps}
    art = Path(str(summary["artifacts_dir"])) if summary.get("artifacts_dir") else None
    functional: dict[str, object] = {}
    governance: dict[str, object] = {}

    # 1-3: install / doctor / index outcomes from the subprocess journey.
    if (work / "opencontext.yaml").is_file():
        functional["create-usable-config"] = _met("install wrote a usable opencontext.yaml")
    if by_step.get("doctor --strict", {}).get("ok"):
        functional["detect-capabilities"] = _met("doctor --strict exited 0")
    if any(work.rglob("project_manifest.json")):
        functional["build-init-kg"] = _met("index produced project_manifest.json")

    # 4-5: workflow selection (the ONE shared selector), provider-free + deterministic.
    if summary.get("workflow") == "oc-flow":
        functional["select-oc-flow-for-bugfix"] = _met(
            f"localized bugfix -> oc-flow ({summary.get('selection_reason')})"
        )
    if select_workflow(_FORMAL_TASK).workflow == "sdd":
        functional["select-sdd-for-formal"] = _met("formal/high-risk task -> sdd")

    # 6-8, 11-14: per-artifact evidence from the completed run (artifacts may live in
    # phase subdirs, e.g. consolidation/, so match by name anywhere under the run dir).
    def _artifact(name: str) -> Path | None:
        if art is None:
            return None
        return next((p for p in art.rglob(name) if p.is_file()), None)

    if summary.get("status") == "completed":
        if (work / "buggy_add.py").read_text(encoding="utf-8") == _FIXED_SRC:
            functional["apply-small-mutation-safely"] = _met("checkpointed edit verified")
        checks = {
            "retrieve-minimal-context": "context-envelope.json",
            "run-local-inspection": "inspection-report.json",
            "persist-artifacts-receipts": "apply-receipts.json",
            "report-cost-confidence": "cost-report.json",
        }
        for gate, fname in checks.items():
            if _artifact(fname) is not None:
                functional[gate] = _met(f"{fname} persisted")
        if _artifact("memory-delta.json") is not None and _artifact("graph-delta.json") is not None:
            functional["update-memory-kg-consolidation"] = _met(
                "consolidation wrote memory-delta + graph-delta"
            )
        summary_md = _artifact("summary.md")
        if summary_md is not None and summary_md.read_text(encoding="utf-8").strip():
            functional["actionable-summary"] = _met("summary.md produced")

    # 9-10: a provider-free mutation run diagnoses a bounded failure and escalates
    # honestly (needs_executor / escalated) rather than faking a completion (B1/B8).
    # 9-10: run on a PROVIDER-LESS project (no test_stub config) so a mutation task
    # honestly hits its bounded budget and escalates — evidences bounded-failure handling
    # + escalation. (``work`` itself carries the test_stub yaml and would complete.)
    try:
        import tempfile

        with tempfile.TemporaryDirectory() as _d:
            pl = Path(_d)
            (pl / "m.py").write_text("def f():\n    return 0\n", encoding="utf-8")
            (pl / "test_m.py").write_text(
                "from m import f\n\n\ndef test_f():\n    assert f() == 1\n", encoding="utf-8"
            )
            free = run_oc_flow_cli(
                "Fix failing test", root=pl, workflow="oc-flow", enabled=True,
                as_json=False, executor=None,
            )
        if free.get("status") in {"needs_executor", "blocked", "escalated"}:
            functional["diagnose-bounded-failures"] = _met(
                f"bounded failure handled provider-free: {free.get('completion_reason')}"
            )
            if free.get("escalated") or free.get("status") in {"needs_executor", "escalated"}:
                functional["escalate-when-needed"] = _met("escalated instead of faking completion")
    except Exception:
        pass

    # 15: resume restores the completed run from its manifest.
    try:
        run_id = str(summary.get("run_id", ""))
        session_id = str(summary.get("session_id", ""))
        if run_id and session_id:
            stub = _StubGateway((work / "provider_stub.json").read_text(encoding="utf-8"))
            ex = ProviderBackedNodeExecutor(gateway=stub, root=work, provider="mock")
            resumed = OCFlowRunner(root=work, executor=ex).resume(session_id, run_id)
            if resumed.contract is not None:
                functional["resume-if-interrupted"] = _met("run restored from manifest")
    except Exception:
        pass

    # D1: traceability — no orphaned requirements in the 54-matrix.
    ok, detail = _traceability_has_no_orphans()
    if ok:
        governance["traceability-no-orphans"] = _met(detail)

    # D2: receipts reconstructable — the run's apply receipts parse + carry entries.
    receipts_path = _artifact("apply-receipts.json")
    if receipts_path is not None:
        try:
            import json as _json

            data = _json.loads(receipts_path.read_text(encoding="utf-8"))
            if isinstance(data.get("receipts"), list):
                governance["receipts-reconstructable"] = _met(
                    f"{len(data['receipts'])} apply receipt(s) reconstructable"
                )
        except Exception:
            pass

    # D3: owner-resolution hooks exist (§9.17 KG-13) even pre-Organization-Graph.
    try:
        from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

        if callable(getattr(KnowledgeGraph, "extract_owners", None)):
            governance["owner-resolution-hooks"] = _met("KnowledgeGraph.extract_owners present")
    except Exception:
        pass

    return functional, governance


def run_dod_journey(
    work: Path, env: dict[str, str]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Drive the audit DoD sequence over the golden bugfix project in ``work``.

    install --yes -> doctor --strict -> index -> run "Fix failing test" --workflow auto
    (REAL CLI subprocess) -> pytest. Returns ``(steps, summary)`` without asserting,
    so both the e2e test and the release-evidence collector
    (``scripts/collect_release_evidence.py``) reuse one journey driver.
    """
    steps: list[dict[str, object]] = []

    r = _cli(["install", "--yes", "."], work, env)
    steps.append({"step": "install", "exit_code": r.returncode, "ok": r.returncode == 0})

    r = _cli(["doctor", "--strict"], work, env)
    steps.append({"step": "doctor --strict", "exit_code": r.returncode, "ok": r.returncode == 0})

    r = _cli(["index", "."], work, env)
    steps.append({"step": "index", "exit_code": r.returncode, "ok": r.returncode == 0})

    # Real-CLI subprocess run (B7): the fixture's `opencontext.yaml` declares
    # `provider: test_stub` + `edits_file`, so the live `opencontext run` resolves the
    # deterministic `TestStubGateway` executor ITSELF and drives the full provider ->
    # validate -> policy -> checkpoint -> apply -> receipt -> inspection pipeline. No
    # in-process executor / runner is constructed; this is the honest DoD product surface.
    r = _cli(["run", "Fix failing test", "--workflow", "auto", "--json"], work, env)
    summary: dict[str, object] = json.loads(r.stdout) if r.stdout.strip() else {}
    steps.append(
        {
            "step": "run",
            "exit_code": r.returncode,
            "status": summary.get("status"),
            "ok": r.returncode == 0 and summary.get("status") == "completed",
        }
    )

    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "test_buggy_add.py"],
        cwd=str(work), capture_output=True, text=True, timeout=180, check=False,
    )
    steps.append({"step": "pytest", "exit_code": p.returncode, "ok": p.returncode == 0})
    return steps, summary


def test_dod_journey_proves_and_meets_e2e_gate(
    isolated_env: tuple[Path, dict[str, str]],
) -> None:
    work, env = isolated_env
    steps, summary = run_dod_journey(work, env)

    # The journey ran cleanly end-to-end (each gating step is a recorded ``ok`` step).
    assert all(bool(s["ok"]) for s in steps), steps
    assert (work / "opencontext.yaml").is_file()
    assert any(work.rglob("project_manifest.json"))
    assert summary["status"] == "completed" and summary["workflow"] == "oc-flow"
    assert (work / "buggy_add.py").read_text(encoding="utf-8") == _FIXED_SRC

    # 6) release acceptance — record the DoD proof, then the e2e-dod gate reads MET.
    passed = all(bool(s["ok"]) for s in steps)
    assert passed
    write_dod_proof(work, passed=passed, steps=steps)
    proof = read_dod_proof(work)
    assert proof is not None and proof["passed"] is True

    verdict = AcceptanceEvaluator(repo_root=work).evaluate(bench_root=str(work), release_mode=True)
    e2e = next(g for g in verdict.gates if g.gate == E2E_DOD_GATE)
    assert e2e.status is GateStatus.MET, e2e.detail
    # The proven DoD + the five golden gates are MET; nothing fabricated; 0 FAILED.
    assert verdict.failed == 0
    golden = {
        g.gate: g.status
        for g in verdict.gates
        if g.gate in {"first-run", "oc-flow-localized-bugfix", "policy-security",
                      "resume-rollback", "provider-fallback"}
    }
    assert all(s is GateStatus.MET for s in golden.values()), golden

    # 7) VDM-007 — write the single B+D evidence artifact from the REAL journey, then
    #    prove `release acceptance` reads it and moves only the evidenced gates to MET.
    functional, governance = _collect_functional_governance(work, steps, summary)
    write_release_evidence(work, functional=functional, governance=governance)
    read_functional, read_governance = read_release_evidence(work)
    assert set(read_functional) == set(functional) and set(read_governance) == set(governance)

    # This bugfix journey genuinely exercises every B + D dimension.
    assert set(functional) == set(FUNCTIONAL_BEHAVIOURS), sorted(
        set(FUNCTIONAL_BEHAVIOURS) - set(functional)
    )
    assert set(governance) == set(GOVERNANCE_GATES), sorted(
        set(GOVERNANCE_GATES) - set(governance)
    )

    injected = AcceptanceEvaluator(repo_root=work).evaluate(
        bench_root=str(work), functional=read_functional, governance=read_governance,
    )
    measured = {g.gate: g.status for g in injected.gates}
    for gate in functional:
        assert measured[gate] is GateStatus.MET, (gate, measured[gate])
    for gate in governance:
        assert measured[gate] is GateStatus.MET, (gate, measured[gate])
    assert injected.failed == 0


def test_unproven_dod_fails_in_release_mode_but_not_dev(tmp_path: Path) -> None:
    # No proof artifact under this root.
    release = AcceptanceEvaluator(repo_root=tmp_path).evaluate(
        bench_root=str(tmp_path), release_mode=True
    )
    e2e_release = next(g for g in release.gates if g.gate == E2E_DOD_GATE)
    assert e2e_release.status is GateStatus.FAILED  # hard gate: 1.0 cannot be declared
    assert release.failed >= 1

    dev = AcceptanceEvaluator(repo_root=tmp_path).evaluate(bench_root=str(tmp_path))
    e2e_dev = next(g for g in dev.gates if g.gate == E2E_DOD_GATE)
    assert e2e_dev.status is GateStatus.NOT_MEASURED  # dev mode keeps the 0-FAILED invariant
