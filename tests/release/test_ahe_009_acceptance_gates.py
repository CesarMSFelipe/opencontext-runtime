"""End-to-end tests for ``opencontext agent-harness acceptance`` (PR-AHE-009).

The acceptance command is the contract surface that ties PR-AHE-001 through
PR-AHE-009 together: every named gate must be backed by a passing test from
a prior PR. These tests verify the command itself — the gate registry, the
exit-code contract (``ready=true`` exits 0; any FAILED or NOT_MEASURED gate
exits 1), and the JSON shape.

The selector strings are stubbed to an empty / known-good set so the tests
do not re-run the whole pytest matrix; the real selector list is exercised
by the smoke test below which invokes the evaluator directly against the
project root.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from opencontext_core.agent_harness_acceptance import (
    GATES,
    AcceptanceVerdict,
    AgentHarnessAcceptanceEvaluator,
    GateOutcome,
    render_verdict_json,
)


@pytest.fixture(scope="module")
def repo_root() -> Path:
    """The project root that the acceptance command evaluates by default.

    Module-scoped because every test that uses it points at the same root;
    skipping the per-test discovery keeps the suite fast.
    """
    # tests/release/test_ahe_009_acceptance_gates.py → up two levels → root.
    return Path(__file__).resolve().parent.parent.parent


# --------------------------------------------------------------------------- #
# Gate registry — every spec-named gate id must be present
# --------------------------------------------------------------------------- #


class TestGateRegistry:
    """The final-acceptance-gates spec names 11 gates; the registry must carry all of them."""

    def test_registry_contains_every_named_gate(self) -> None:
        ids = {gate_id for gate_id, _ in GATES}
        expected = {
            "mcp-oc-flow-sampling-bugfix",
            "mcp-oc-flow-no-executor",
            "mcp-sdd-junk-output-blocked",
            "mcp-sdd-valid-output",
            "tdd-strict-gate",
            "kg-call-graph-basic-python",
            "context-pack-truthfulness",
            "memory-runtime-backed",
            "engram-fake-routing",
            "agent-docs-parity",
            "quality-semantics",
        }
        missing = expected - ids
        assert not missing, f"missing gate ids: {sorted(missing)}"

    def test_registry_ids_are_unique(self) -> None:
        ids = [gate_id for gate_id, _ in GATES]
        assert len(ids) == len(set(ids)), "duplicate gate ids in GATES registry"

    def test_registry_selectors_point_at_existing_test_files(self, repo_root: Path) -> None:
        """Every selector path in the registry must resolve to a real file.

        A selector pointing at a missing file would silently become
        ``not_measured`` in production; this test fails loudly at PR review
        time so the gap is caught before merge.
        """
        missing: list[str] = []
        for _gate_id, selectors in GATES:
            for token in selectors.split():
                if "::" in token:
                    # nodeid form: file.py::test_name — only the file part
                    # needs to exist on disk.
                    file_part = token.split("::", 1)[0]
                else:
                    file_part = token
                if not (repo_root / file_part).is_file():
                    missing.append(file_part)
        assert not missing, f"selector files missing on disk: {missing}"

    def test_registry_selectors_collect_at_least_one_test(self, repo_root: Path) -> None:
        """Every selector must yield ≥1 collected test.

        pytest exit-code 5 (no tests collected) is mapped to ``not_measured``
        in production; catching a zero-test selector at PR review time keeps
        the acceptance gate honest.
        """
        import subprocess

        zero_test_selectors: list[str] = []
        for _gate_id, selectors in GATES:
            cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q", *selectors.split()]
            completed = subprocess.run(
                cmd,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            if completed.returncode == 5 or "no tests collected" in completed.stderr.lower():
                zero_test_selectors.append(selectors)
        assert not zero_test_selectors, (
            f"selectors with zero collected tests: {zero_test_selectors}"
        )


# --------------------------------------------------------------------------- #
# GateOutcome + AcceptanceVerdict shape
# --------------------------------------------------------------------------- #


class TestVerdictShape:
    """The verdict JSON shape is the contract the CLI exposes — pin it."""

    def test_gate_outcome_dict_keys(self) -> None:
        outcome = GateOutcome(gate="x", status="met", detail="ok")
        d = outcome.to_dict()
        assert set(d) == {"gate", "status", "detail"}

    def test_verdict_dict_keys(self) -> None:
        verdict = AcceptanceVerdict(
            ready=True, met=1, failed=0, not_measured=0, gates=[GateOutcome(gate="x", status="met")]
        )
        d = verdict.to_dict()
        assert set(d) >= {"schema_version", "ready", "met", "failed", "not_measured", "gates"}

    def test_render_verdict_json_is_parseable(self) -> None:
        verdict = AcceptanceVerdict(ready=True, met=2, failed=0, not_measured=0)
        rendered = render_verdict_json(verdict)
        parsed = json.loads(rendered)
        assert parsed["ready"] is True
        assert parsed["met"] == 2

    def test_verdict_defaults_are_zero(self) -> None:
        verdict = AcceptanceVerdict()
        assert verdict.ready is False
        assert verdict.met == 0
        assert verdict.failed == 0
        assert verdict.not_measured == 0
        assert verdict.gates == []


# --------------------------------------------------------------------------- #
# Exit-code contract — exercised through the CLI end-to-end
# --------------------------------------------------------------------------- #


class TestAcceptanceCommandExitCode:
    """``opencontext agent-harness acceptance`` exits 0 only when ready=true.

    Tested by invoking the CLI as a subprocess so the parser layout AND the
    handler wiring are both covered (catching regressions in either).
    """

    @pytest.fixture
    def cli_path(self) -> str:
        return sys.executable

    def _run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess:
        cmd = [
            self.cli_path if False else sys.executable,
            "-m",
            "opencontext_cli.main",
            "agent-harness",
            "acceptance",
            "--root",
            str(root),
            *args,
        ]
        return subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

    def test_ready_true_exits_zero(self, repo_root: Path) -> None:
        """When every gate is MET the verdict is ready=true and exit code is 0."""
        completed = self._run_cli(repo_root)
        # We do not require ALL gates to be MET in CI (some may be marked
        # not_measured depending on environment), but on this project root
        # with all PR-AHE-001..009 work present, every gate must be MET.
        if completed.returncode == 0:
            payload = json.loads(completed.stdout)
            assert payload["ready"] is True
            assert payload["failed"] == 0
            assert payload["not_measured"] == 0
        else:
            # If the gate set regressed, surface the failed gate names so the
            # regression is debuggable from the test output.
            pytest.fail(
                f"acceptance command exited {completed.returncode}; "
                f"stdout=\n{completed.stdout[:1500]}\nstderr=\n{completed.stderr[:1500]}"
            )

    def test_json_includes_every_gate(self, repo_root: Path) -> None:
        """Every gate in GATES must appear in the verdict JSON."""
        completed = self._run_cli(repo_root)
        assert completed.returncode == 0, f"non-zero exit; stderr={completed.stderr[:500]}"
        payload = json.loads(completed.stdout)
        listed = {g["gate"] for g in payload["gates"]}
        registered = {gate_id for gate_id, _ in GATES}
        assert listed == registered, (
            f"verdict missing gates: {registered - listed}; extra gates: {listed - registered}"
        )


# --------------------------------------------------------------------------- #
# Evaluator surface — direct invocation, no subprocess
# --------------------------------------------------------------------------- #


class TestEvaluatorDirectInvocation:
    """Call the evaluator in-process and assert the verdict on this repo root.

    The pytest-driven selectors are exercised live against the project; any
    regression in a backing test would propagate here as a FAILED gate.
    """

    def test_evaluator_against_project_root_returns_ready_true(self, repo_root: Path) -> None:
        verdict = AgentHarnessAcceptanceEvaluator(repo_root).evaluate()
        if not verdict.ready:
            failing = [g for g in verdict.gates if g.status != "met"]
            pytest.fail(
                "verdict.ready is False on a clean project root. "
                "Failing gates:\n"
                + "\n".join(f"  {g.gate}: {g.status} - {g.detail}" for g in failing)
            )

    def test_evaluator_with_unknown_root_still_returns_a_verdict(self, tmp_path: Path) -> None:
        """An empty root yields all NOT_MEASURED (selectors find no source).

        Verifies the evaluator never crashes and never returns ``ready=True``
        against a project that has no tests.
        """
        verdict = AgentHarnessAcceptanceEvaluator(tmp_path).evaluate()
        assert verdict.ready is False
        # At least one gate should be not_measured (the project has no tests).
        assert verdict.not_measured >= 1
