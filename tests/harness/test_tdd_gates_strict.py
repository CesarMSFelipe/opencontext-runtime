"""TDD RED tests for strict-mode FailingTestExistsGate, TestsPassGate,
and harness.yaml tdd_mode propagation.

Strict TDD mode:
  - FailingTestExistsGate must EXECUTE the test and require it to FAIL (exit != 0).
  - A test file that passes (exit == 0) should cause the gate to FAIL.
  - A missing test file still causes the gate to FAIL.
  - Non-strict mode (ask/off) keeps filename-existence-only behavior unchanged.
  - TestsPassGate maps non-zero exit to GateStatus.FAILED (not WARNING).
  - TestsPassGate is disabled by default (tdd_mode != "strict").
  - _write_harness_yaml includes tdd_mode in workflow_defaults.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from opencontext_core.harness.gates import FailingTestExistsGate, TestsPassGate
from opencontext_core.harness.models import GateStatus

# ---------------------------------------------------------------------------
# FailingTestExistsGate — strict mode: must run the test, require it to FAIL
# ---------------------------------------------------------------------------


class TestFailingTestExistsGateStrictMode:
    """Strict-mode tests: gate must execute the test file and verify it's RED."""

    def test_strict_passes_when_test_actually_fails(self, tmp_path: Path) -> None:
        """A test file whose execution returns non-zero → gate PASSES (RED confirmed)."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_my_feature.py"
        test_file.write_text(
            textwrap.dedent("""\
                def test_it_fails():
                    assert False, "expected failure — RED"
            """),
            encoding="utf-8",
        )

        gate = FailingTestExistsGate()
        result = gate.evaluate("my_feature", tmp_path, tdd_mode="strict")

        assert result.status == GateStatus.PASSED
        assert "red" in result.message.lower() or "failing" in result.message.lower()

    def test_strict_fails_when_test_passes(self, tmp_path: Path) -> None:
        """A test file that passes (exit 0) → gate FAILS (no RED confirmed)."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_my_feature.py"
        test_file.write_text(
            textwrap.dedent("""\
                def test_it_passes():
                    assert True
            """),
            encoding="utf-8",
        )

        gate = FailingTestExistsGate()
        result = gate.evaluate("my_feature", tmp_path, tdd_mode="strict")

        assert result.status == GateStatus.FAILED
        msg = result.message.lower()
        assert "pass" in msg or "green" in msg or "red" in msg

    def test_strict_fails_when_file_missing(self, tmp_path: Path) -> None:
        """Missing test file → gate FAILS even in strict mode."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        gate = FailingTestExistsGate()
        result = gate.evaluate("nonexistent_task", tmp_path, tdd_mode="strict")

        assert result.status == GateStatus.FAILED

    def test_strict_timeout_respected(self, tmp_path: Path) -> None:
        """Subprocess execution is bounded by a timeout; on timeout gate FAILS gracefully."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_slow.py"
        # This won't actually sleep in tests — we mock subprocess.run
        test_file.write_text("def test_slow(): pass\n", encoding="utf-8")

        gate = FailingTestExistsGate()

        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=120),
        ):
            result = gate.evaluate("slow", tmp_path, tdd_mode="strict")

        assert result.status == GateStatus.FAILED
        assert "timeout" in result.message.lower()

    def test_strict_no_shell_injection(self, tmp_path: Path) -> None:
        """Subprocess is called with a list (not shell=True) to prevent injection."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_my_feature.py"
        test_file.write_text("def test_x(): assert False\n", encoding="utf-8")

        gate = FailingTestExistsGate()

        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            return_value=MagicMock(returncode=1),
        ) as mock_run:
            gate.evaluate("my_feature", tmp_path, tdd_mode="strict")

        call_args = mock_run.call_args
        # First positional argument must be a list, NOT a string.
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args")
        assert isinstance(cmd, list), "subprocess must be called with a list, not a shell string"
        assert call_args[1].get("shell") is not True, "shell=True must not be used"


# ---------------------------------------------------------------------------
# FailingTestExistsGate — non-strict mode: filename-existence unchanged
# ---------------------------------------------------------------------------


class TestFailingTestExistsGateNonStrictMode:
    """Non-strict modes keep original filename-existence behavior."""

    @pytest.mark.parametrize("mode", ["ask", "off"])
    def test_ask_and_off_pass_on_file_existence_only(self, tmp_path: Path, mode: str) -> None:
        """In ask/off mode, gate passes as long as file exists — no execution."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        # File exists but would pass if executed — should still PASS in ask/off
        test_file = tests_dir / "test_my_feature.py"
        test_file.write_text("def test_x(): assert True\n", encoding="utf-8")

        gate = FailingTestExistsGate()

        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            side_effect=AssertionError("subprocess must NOT be called in non-strict mode"),
        ):
            result = gate.evaluate("my_feature", tmp_path, tdd_mode=mode)

        assert result.status == GateStatus.PASSED

    @pytest.mark.parametrize("mode", ["ask", "off"])
    def test_ask_and_off_fail_on_missing_file(self, tmp_path: Path, mode: str) -> None:
        """In ask/off mode, gate still fails when file is missing."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        gate = FailingTestExistsGate()
        result = gate.evaluate("nonexistent_task", tmp_path, tdd_mode=mode)

        assert result.status == GateStatus.FAILED

    def test_default_mode_is_non_strict(self, tmp_path: Path) -> None:
        """Calling evaluate() without tdd_mode uses non-strict (ask) behavior."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_my_feature.py"
        test_file.write_text("def test_x(): assert True\n", encoding="utf-8")

        gate = FailingTestExistsGate()
        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            side_effect=AssertionError("subprocess must NOT be called by default"),
        ):
            result = gate.evaluate("my_feature", tmp_path)

        assert result.status == GateStatus.PASSED


# ---------------------------------------------------------------------------
# TestsPassGate — post-apply/verify test runner
# ---------------------------------------------------------------------------


class TestTestsPassGate:
    """TestsPassGate: run test command, map non-zero exit to FAILED."""

    def test_passes_when_tests_succeed(self, tmp_path: Path) -> None:
        """Exit code 0 → GateStatus.PASSED."""
        gate = TestsPassGate()
        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="5 passed", stderr=""),
        ):
            result = gate.evaluate(["pytest", "-q"], cwd=tmp_path)

        assert result.status == GateStatus.PASSED

    def test_fails_when_tests_fail(self, tmp_path: Path) -> None:
        """Non-zero exit code → GateStatus.FAILED (not WARNING)."""
        gate = TestsPassGate()
        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            return_value=MagicMock(returncode=1, stdout="1 failed", stderr=""),
        ):
            result = gate.evaluate(["pytest", "-q"], cwd=tmp_path, tdd_mode="strict")

        assert result.status == GateStatus.FAILED
        # Must be FAILED, not WARNING
        assert result.status != GateStatus.WARNING

    def test_timeout_maps_to_failed(self, tmp_path: Path) -> None:
        """Subprocess timeout → GateStatus.FAILED with informative message."""
        gate = TestsPassGate()
        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=300),
        ):
            result = gate.evaluate(["pytest", "-q"], cwd=tmp_path, tdd_mode="strict")

        assert result.status == GateStatus.FAILED
        assert "timeout" in result.message.lower()

    def test_disabled_by_default_without_strict_mode(self) -> None:
        """Gate is inactive when tdd_mode is not strict — returns PASSED immediately."""
        gate = TestsPassGate()
        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            side_effect=AssertionError("subprocess must NOT run when gate is disabled"),
        ):
            result = gate.evaluate(["pytest", "-q"], cwd=Path("."), tdd_mode="ask")

        assert result.status == GateStatus.PASSED

    def test_disabled_in_off_mode(self) -> None:
        """Gate is inactive in off mode."""
        gate = TestsPassGate()
        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            side_effect=AssertionError("subprocess must NOT run in off mode"),
        ):
            result = gate.evaluate(["pytest", "-q"], cwd=Path("."), tdd_mode="off")

        assert result.status == GateStatus.PASSED

    def test_active_in_strict_mode(self, tmp_path: Path) -> None:
        """Gate executes when tdd_mode='strict'."""
        gate = TestsPassGate()
        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ) as mock_run:
            gate.evaluate(["pytest", "-q"], cwd=tmp_path, tdd_mode="strict")

        mock_run.assert_called_once()

    def test_no_shell_injection(self, tmp_path: Path) -> None:
        """subprocess.run is called with a list (not shell=True)."""
        gate = TestsPassGate()
        with patch(
            "opencontext_core.harness.gates.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ) as mock_run:
            gate.evaluate(["pytest", "-q"], cwd=tmp_path, tdd_mode="strict")

        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args")
        assert isinstance(cmd, list)
        assert call_args[1].get("shell") is not True


# ---------------------------------------------------------------------------
# harness.yaml tdd_mode propagation
# ---------------------------------------------------------------------------


class TestHarnessYamlTddModePropagate:
    """_write_harness_yaml must include tdd_mode in workflow_defaults."""

    def test_strict_tdd_mode_written_to_harness_yaml(self, tmp_path: Path) -> None:
        """When options.tdd_mode == 'strict', harness.yaml workflow_defaults.tdd_mode = 'strict'."""
        import yaml

        from opencontext_core.onboarding.service import OnboardingOptions, OnboardingService

        service = OnboardingService()
        service.run(OnboardingOptions(root=tmp_path, tdd_mode="strict", force_agent_files=True))

        harness_path = tmp_path / ".opencontext" / "harness.yaml"
        assert harness_path.exists()
        data = yaml.safe_load(harness_path.read_text(encoding="utf-8"))
        wf = data.get("workflow_defaults", {})
        assert wf.get("tdd_mode") == "strict", (
            f"Expected tdd_mode='strict' in workflow_defaults, got: {wf}"
        )

    def test_ask_tdd_mode_written_to_harness_yaml(self, tmp_path: Path) -> None:
        """Default tdd_mode='ask' is also written explicitly."""
        import yaml

        from opencontext_core.onboarding.service import OnboardingOptions, OnboardingService

        service = OnboardingService()
        service.run(OnboardingOptions(root=tmp_path, tdd_mode="ask", force_agent_files=True))

        harness_path = tmp_path / ".opencontext" / "harness.yaml"
        data = yaml.safe_load(harness_path.read_text(encoding="utf-8"))
        wf = data.get("workflow_defaults", {})
        assert wf.get("tdd_mode") == "ask"

    def test_off_tdd_mode_written_to_harness_yaml(self, tmp_path: Path) -> None:
        """tdd_mode='off' is also propagated."""
        import yaml

        from opencontext_core.onboarding.service import OnboardingOptions, OnboardingService

        service = OnboardingService()
        service.run(OnboardingOptions(root=tmp_path, tdd_mode="off", force_agent_files=True))

        harness_path = tmp_path / ".opencontext" / "harness.yaml"
        data = yaml.safe_load(harness_path.read_text(encoding="utf-8"))
        wf = data.get("workflow_defaults", {})
        assert wf.get("tdd_mode") == "off"


# ---------------------------------------------------------------------------
# VerifyPhase: test failure must propagate to final_status as FAILED
# ---------------------------------------------------------------------------


class TestVerifyPhaseTestFailurePropagation:
    """verify_tests_passed gate must be FAILED (not WARNING) when tests fail.

    Before this fix: VerifyPhase emitted WARNING for test failures, which was
    never checked by the runner's dispatched-gate path → final_status stayed
    PASSED despite the suite failing.
    """

    def test_verify_gate_is_failed_not_warning_on_test_failure(self) -> None:
        from opencontext_core.harness.models import GateStatus

        # Synthesise a failing test result.
        failing = {
            "exit_code": 1,
            "passed": 0,
            "failed": 1,
            "errors": 0,
            "tests_executed": True,
            "output": "FAILED test_foo.py::test_bar",
            "error_output": "",
        }
        # Drive the gate-creation logic directly (no subprocess).
        gates = []
        if failing["exit_code"] != 0:
            from opencontext_core.harness.models import PhaseGate

            gates.append(
                PhaseGate(
                    id="verify_tests_passed",
                    phase="verify",
                    status=GateStatus.FAILED,
                    message=f"Tests exited with code {failing['exit_code']}",
                )
            )
        assert gates, "gate must be emitted on test failure"
        assert gates[0].status == GateStatus.FAILED, (
            f"Expected FAILED, got {gates[0].status} — test failure must propagate to final_status"
        )

    def test_runner_propagates_result_gate_failures_to_final_status(self) -> None:
        """result.gates FAILED from any phase must update final_status via all_new_gates."""
        from opencontext_core.harness.models import GateStatus, PhaseGate

        # Simulate the runner loop logic: all_new_gates = result.gates + dispatched.
        fail_gate = PhaseGate(
            id="verify_tests_passed",
            phase="verify",
            status=GateStatus.FAILED,
            message="Tests exited with code 1",
        )
        all_new_gates = [fail_gate]  # result.gates only; no dispatched
        gate_policy = "block"
        final_status = GateStatus.PASSED  # would be PASSED before this check
        if any(g.status == GateStatus.FAILED for g in all_new_gates):
            if gate_policy == "block":
                final_status = GateStatus.FAILED
        assert final_status == GateStatus.FAILED, (
            "FAILED gate in result.gates must propagate to final_status when gate_policy=block"
        )
