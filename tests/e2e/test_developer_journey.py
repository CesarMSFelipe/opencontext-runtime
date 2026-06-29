"""E2E DoD developer journey + the hard ``e2e-dod`` acceptance gate (B10 / AVH-010 / AVH-017).

Drives the audit Definition-of-Done sequence end-to-end on the golden bugfix fixture:

    install --yes -> doctor --strict -> index -> run "Fix failing test" --workflow auto
    -> pytest <golden> -> release acceptance

The ``run`` step is driven IN-PROCESS through the Phase-3 injectable
``ProviderBackedNodeExecutor`` with a DETERMINISTIC provider stub (the fixture's
``provider_stub.json``): the CLI cannot inject a stub, and OC Flow ships default-off
until the Phase-8 flag flip, so the harness enables it and supplies the stub. This is
honest — the full provider -> validate -> policy -> checkpoint -> apply -> receipt ->
inspection pipeline runs; only the model is a deterministic stand-in.

A proven sequence writes the DoD proof artifact; the mandatory ``e2e-dod`` gate then
reads ``MET``. An UNPROVEN sequence FAILS the gate in release mode (hard 1.0 gate) and
is honestly ``NOT_MEASURED`` in dev mode.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from opencontext_core.evaluation.models import GateStatus
from opencontext_core.models.llm import LLMResponse
from opencontext_core.oc_flow.cli import run_oc_flow_cli
from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor
from opencontext_core.operating_model.release_gate import (
    E2E_DOD_GATE,
    AcceptanceEvaluator,
    read_dod_proof,
    write_dod_proof,
)


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


def _cli(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "opencontext_cli.main", *argv],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=240, check=False,
    )


def test_dod_journey_proves_and_meets_e2e_gate(
    isolated_env: tuple[Path, dict[str, str]],
) -> None:
    work, env = isolated_env
    steps: list[dict[str, object]] = []

    # 1) install --yes .
    r = _cli(["install", "--yes", "."], work, env)
    steps.append({"step": "install", "exit_code": r.returncode, "ok": r.returncode == 0})
    assert r.returncode == 0, r.stdout + r.stderr
    assert (work / "opencontext.yaml").is_file()

    # 2) doctor --strict
    r = _cli(["doctor", "--strict"], work, env)
    steps.append({"step": "doctor --strict", "exit_code": r.returncode, "ok": r.returncode == 0})
    assert r.returncode == 0, r.stdout + r.stderr

    # 3) index .
    r = _cli(["index", "."], work, env)
    steps.append({"step": "index", "exit_code": r.returncode, "ok": r.returncode == 0})
    assert r.returncode == 0, r.stdout + r.stderr
    assert any(work.rglob("project_manifest.json"))

    # 4) run "Fix failing test" --workflow auto  (in-process, stub-driven, enabled)
    stub = _StubGateway((work / "provider_stub.json").read_text(encoding="utf-8"))
    executor = ProviderBackedNodeExecutor(gateway=stub, root=work, provider="mock")
    summary = run_oc_flow_cli(
        "Fix failing test", root=work, workflow="auto", enabled=True,
        as_json=False, executor=executor,
    )
    completed = summary["status"] == "completed"
    steps.append({"step": "run", "status": summary["status"], "ok": completed})
    assert summary["status"] == "completed"
    assert summary["workflow"] == "oc-flow"
    assert stub.calls  # the real pipeline called the provider
    fixed = (work / "buggy_add.py").read_text(encoding="utf-8")
    assert fixed == "def add(a, b):\n    return a + b\n"

    # 5) pytest <golden>
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "test_buggy_add.py"],
        cwd=str(work), capture_output=True, text=True, timeout=180, check=False,
    )
    steps.append({"step": "pytest", "exit_code": p.returncode, "ok": p.returncode == 0})
    assert p.returncode == 0, p.stdout + p.stderr

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
