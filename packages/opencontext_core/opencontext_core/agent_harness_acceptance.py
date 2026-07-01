"""Agent/Harness acceptance gate set (PR-AHE-009 / final-acceptance-gates).

Each gate is a contract claim backed by an existing pytest selector from
PR-AHE-001 through PR-AHE-009. The :class:`AgentHarnessAcceptanceEvaluator`
runs every selector through the project's ``pytest`` and aggregates the
outcomes into one honest verdict — ``ready`` only when every gate is MET.

The intent matches the spec's "coherent Quality Result Fields" rule: a gate
that did not run is reported as ``NOT_MEASURED`` (never a fake pass); a gate
that ran and failed is ``FAILED``. The CLI command
``opencontext agent-harness acceptance --root .`` calls this evaluator and
prints the verdict as JSON.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Gate definitions ────────────────────────────────────────────────────────
#
# Each gate is ``(id, selectors)``. A selector is one pytest ``nodeid`` (file
# path or ``file::test_name``). Multiple selectors are joined with a space —
# pytest runs them as a single invocation so the gate's pass/fail is one
# binary outcome (the spec never asks for partial gates).
#
# The selectors point to existing tests from the prior PR chain. The
# quality-semantics gate points at the new tests/mcp/test_quality_semantics.py
# from this PR.

GATES: tuple[tuple[str, str], ...] = (
    (
        "mcp-oc-flow-sampling-bugfix",
        "tests/mcp/test_mcp_sampling_executor.py",
    ),
    (
        "mcp-oc-flow-no-executor",
        "tests/core/test_mcp_run_contract.py::test_oc_flow_run_without_executor_cannot_complete",
    ),
    (
        "mcp-sdd-junk-output-blocked",
        "tests/core/test_mcp_run_contract.py::test_mcp_sdd_junk_phase_output_surfaces_warning",
    ),
    (
        "mcp-sdd-valid-output",
        "tests/core/test_mcp_run_contract.py::test_sdd_run_includes_phase_metadata",
    ),
    (
        "tdd-strict-gate",
        "tests/harness/test_tdd_pre_gate.py tests/harness/test_default_config_posture.py",
    ),
    (
        "kg-call-graph-basic-python",
        "tests/golden/test_kg_call_graph_python.py",
    ),
    (
        "context-pack-truthfulness",
        "tests/context/test_pack_truthfulness.py",
    ),
    (
        "memory-runtime-backed",
        "tests/mcp/test_mcp_memory_runtime_backed.py",
    ),
    (
        "engram-fake-routing",
        "tests/memory/test_composite_routing.py tests/memory/test_fake_engram_client.py",
    ),
    (
        "agent-docs-parity",
        "tests/agents/test_template_renderer.py "
        "tests/docs/test_ahe_008_setup_docs.py "
        "tests/configurator/test_ahe_008_setup_outputs.py",
    ),
    (
        "quality-semantics",
        "tests/mcp/test_quality_semantics.py",
    ),
)


# ── Result shape ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateOutcome:
    """The honest outcome of running one gate's pytest selector."""

    gate: str
    status: str  # "met" | "failed" | "not_measured"
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"gate": self.gate, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class AcceptanceVerdict:
    """The agent/harness readiness verdict over the named gate set.

    Mirrors the shape used by the existing ``release acceptance`` evaluator
    so callers can read either verdict uniformly. ``ready`` is True only when
    every gate is MET — a single FAILED or NOT_MEASURED gate blocks readiness
    (the spec's "every named gate ID as met" requirement).
    """

    schema_version: str = "opencontext.agent_harness_acceptance.v1"
    ready: bool = False
    met: int = 0
    failed: int = 0
    not_measured: int = 0
    gates: list[GateOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ready": self.ready,
            "met": self.met,
            "failed": self.failed,
            "not_measured": self.not_measured,
            "gates": [g.to_dict() for g in self.gates],
        }


# ── Evaluator ───────────────────────────────────────────────────────────────


class AgentHarnessAcceptanceEvaluator:
    """Run every named gate's pytest selector and compose the verdict.

    The evaluator spawns ``pytest`` once per gate (so a failure in one gate
    does not pollute another's results). Each selector is run from the
    supplied ``root`` so the verdict always reflects the project the user
    pointed at, not whatever cwd the CLI happens to be in.

    A selector whose pytest invocation fails before it can run (e.g. the file
    is missing, the syntax is broken, or pytest itself is unavailable) is
    reported as ``NOT_MEASURED`` with the subprocess error in ``detail`` —
    the gate did not pass, but it also did not fail in any meaningful sense.
    """

    def __init__(self, repo_root: Path | str = ".") -> None:
        self.repo_root = Path(repo_root).resolve()

    def evaluate(self) -> AcceptanceVerdict:
        outcomes: list[GateOutcome] = []
        for gate_id, selectors in GATES:
            outcome = self._run_one(gate_id, selectors)
            outcomes.append(outcome)

        met = sum(1 for o in outcomes if o.status == "met")
        failed = sum(1 for o in outcomes if o.status == "failed")
        not_measured = sum(1 for o in outcomes if o.status == "not_measured")
        ready = failed == 0 and not_measured == 0 and met == len(GATES)
        return AcceptanceVerdict(
            ready=ready,
            met=met,
            failed=failed,
            not_measured=not_measured,
            gates=outcomes,
        )

    def _run_one(self, gate_id: str, selectors: str) -> GateOutcome:
        """Run one gate's selector and map the pytest exit code to a GateOutcome.

        Exit-code mapping (deterministic, mirrors ``ci-check run``):

        * ``0``  — all tests collected passed → ``met``
        * ``4``  — pytest cmdline error (e.g. selector file does not exist)
          → ``not_measured`` with the pytest error in detail
        * ``5``  — pytest collected zero tests (selector exists but no test
          matched the pattern) → ``not_measured`` with a clear detail
        * any other non-zero exit → ``failed`` (at least one selected test
          failed)
        * subprocess could not start (pytest missing, broken venv, …) →
          ``not_measured`` so the verdict does not falsely claim a FAILED
          status for an infrastructure issue
        """
        cmd: list[str] = [sys.executable, "-m", "pytest", "-q"]
        cmd.extend(selectors.split())
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return GateOutcome(
                gate=gate_id,
                status="not_measured",
                detail=f"pytest could not run for this gate: {exc}",
            )

        if completed.returncode == 0:
            return GateOutcome(gate=gate_id, status="met", detail="pytest exit 0")

        if completed.returncode == 4:
            # pytest cmdline error — selector file does not exist or pattern
            # is malformed. Per spec task 9.15 this is NOT_MEASURED (the gate
            # has no source), not FAILED.
            tail = (completed.stdout + completed.stderr).strip().splitlines()
            last = tail[-1] if tail else "pytest cmdline error"
            return GateOutcome(
                gate=gate_id,
                status="not_measured",
                detail=f"selector unavailable ({last.strip()})",
            )

        if completed.returncode == 5:
            # pytest "no tests ran" — selector exists but no test matched.
            tail = (completed.stdout + completed.stderr).strip().splitlines()
            last = tail[-1] if tail else "no tests collected"
            return GateOutcome(
                gate=gate_id,
                status="not_measured",
                detail=f"no tests collected for selector ({last.strip()})",
            )

        return GateOutcome(
            gate=gate_id,
            status="failed",
            detail=_first_failure_line(completed.stdout, completed.stderr),
        )


def _first_failure_line(stdout: str, stderr: str) -> str:
    """Pick one short failure-line from the pytest output for the gate detail.

    The full pytest output is not in the verdict JSON (it can be hundreds of
    lines per gate); the detail string is the single most informative line
    so a reader scanning the JSON can see WHY each gate failed without
    re-running pytest.
    """
    text = (stdout or "") + "\n" + (stderr or "")
    for line in text.splitlines():
        stripped = line.strip()
        # Pytest failure markers (in order of usefulness).
        if "FAILED" in stripped and "::" in stripped:
            return stripped[:240]
        if stripped.startswith("E   "):
            return stripped[4:][:240]
        if "AssertionError" in stripped:
            return stripped[:240]
        if stripped.startswith("short test summary info"):
            # Next line is the failure list; include the header so the reader
            # knows the tail is a failure summary, not pass output.
            return stripped[:240]
    # Last-resort: return the last non-empty line of the combined output.
    nonempty = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return (nonempty[-1] if nonempty else "pytest reported a failure")[:240]


def render_verdict_json(verdict: AcceptanceVerdict) -> str:
    """Render the verdict as JSON suitable for stdout in the CLI."""
    return json.dumps(verdict.to_dict(), indent=2)


__all__ = [
    "GATES",
    "AcceptanceVerdict",
    "AgentHarnessAcceptanceEvaluator",
    "GateOutcome",
    "render_verdict_json",
]


def _smoke() -> None:  # pragma: no cover — manual smoke only
    """Run the evaluator on the project root and print the verdict.

    Invoked when the module is run as a script: ``python -m
    opencontext_core.agent_harness_acceptance``. Useful for sanity checks
    outside the CLI.
    """
    evaluator = AgentHarnessAcceptanceEvaluator(".")
    print(render_verdict_json(evaluator.evaluate()))


if __name__ == "__main__":  # pragma: no cover
    _smoke()
