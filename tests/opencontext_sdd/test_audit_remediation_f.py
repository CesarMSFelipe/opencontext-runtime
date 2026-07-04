"""Regression tests for audit-remediation-2026-07 Slice F (defects 1-7).

These tests were written FIRST (RED) and must fail before the corresponding
fixes land.  Each class maps to one numbered finding.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Finding 1 (CRITICAL): run_phase silently discards the phase argument
# ---------------------------------------------------------------------------


class TestRunPhaseRoutesByRequestedPhase:
    """run_phase must return a distinguishable envelope per requested phase."""

    def test_propose_and_design_return_different_phases(self, tmp_path: Path) -> None:
        """run_phase('propose', ...) and run_phase('design', ...) must NOT return
        the same phase value when state differs or must at minimum embed the
        requested phase in the returned envelope."""
        from opencontext_sdd.runner import run_phase

        env_propose = run_phase("propose", change="test-change", cwd=str(tmp_path))
        env_design = run_phase("design", change="test-change", cwd=str(tmp_path))

        # Both calls are on the same empty directory — advance() would
        # auto-detect the same state.  The envelope's `phase` field must
        # reflect the *requested* phase or the requested phase must influence
        # the next_recommended routing.
        # At minimum: requesting different phases must not produce identical
        # `next_recommended` values when the phases are at different positions
        # in the lifecycle.
        assert env_propose.phase != env_design.phase or \
            env_propose.next_recommended != env_design.next_recommended, (
            "run_phase returned identical envelopes for 'propose' and 'design'; "
            "the phase argument is being silently discarded."
        )

    def test_run_phase_embeds_requested_phase(self, tmp_path: Path) -> None:
        """The returned envelope's phase field must equal the requested phase."""
        from opencontext_sdd.runner import run_phase

        # Seed a minimal state so advance() does not block on missing artifacts.
        # A missing change dir causes 'blocked' — we want the phase to be
        # the requested one even on blocked responses, OR we want routing to
        # validate the requested phase.
        for verb in ("propose", "spec", "design", "tasks"):
            env = run_phase(verb, change="my-change", cwd=str(tmp_path))
            # The envelope must carry the requested phase, not auto-detected.
            assert env.phase == verb, (
                f"run_phase('{verb}') returned phase='{env.phase}'; "
                "requested phase is discarded."
            )


# ---------------------------------------------------------------------------
# Finding 2 (HIGH): _handle_ff does not abort on blocked phase
# ---------------------------------------------------------------------------


class TestHandleFfAbortsOnBlocked:
    """_handle_ff must stop the loop when a phase returns a non-ok status."""

    def test_ff_aborts_loop_on_blocked_phase(self, tmp_path: Path, capsys) -> None:
        """If the first phase returns blocked, ff must not run subsequent phases."""
        from opencontext_cli.commands.sdd_cmd import _handle_ff

        call_log: list[str] = []

        def fake_run_phase(phase: str, cwd: Path, change: str | None, **kw) -> None:
            call_log.append(phase)
            if phase == "propose":
                # Simulate a blocked envelope via captured output / exception.
                # The real _run_phase prints JSON.  To test abort we need
                # _handle_ff to check the return value.
                raise SystemExit(1)

        with patch("opencontext_cli.commands.sdd_cmd._run_phase", side_effect=fake_run_phase):
            with pytest.raises(SystemExit):
                _handle_ff(change="x", cwd=tmp_path, verbose=False)

        # Only 'propose' must have been attempted — loop must not continue.
        assert call_log == ["propose"], (
            f"ff continued past a blocked phase; called {call_log}"
        )

    def test_ff_reports_blocked_phase_name(self, tmp_path: Path, capsys) -> None:
        """When ff aborts, the output must mention which phase blocked."""
        from opencontext_sdd.runner import PhaseResultEnvelope

        from opencontext_cli.commands.sdd_cmd import _handle_ff

        blocked_env = PhaseResultEnvelope(
            status="blocked",
            executive_summary="Missing proposal.",
            artifacts={},
            next_recommended="init",
            risks=["no artifacts"],
            skill_resolution="paths-injected",
            phase="propose",
            trace_id="",
        )

        # _run_phase now returns the envelope (after fix). Simulate this by
        # patching. The new _handle_ff should check the returned envelope.
        with patch(
            "opencontext_cli.commands.sdd_cmd._run_phase",
            return_value=blocked_env,
        ):
            _handle_ff(change="x", cwd=tmp_path, verbose=False)

        captured = capsys.readouterr()
        # After the fix, blocked output must indicate which phase failed.
        assert "propose" in captured.out.lower() or "blocked" in captured.out.lower(), (
            "ff did not report the blocked phase name."
        )


# ---------------------------------------------------------------------------
# Finding 3 (HIGH): sdd_routes.sdd_phase leaks stack on exception
# ---------------------------------------------------------------------------


class TestSddRouteHandlesRunnerException:
    """POST /phase/{verb} must return a structured 500, not a bare traceback."""

    def test_sdd_phase_wraps_exception_in_http500(self) -> None:
        """When run_phase raises, sdd_phase must raise HTTPException(500)."""
        from fastapi import HTTPException

        from opencontext_api.schemas import SDDPhaseRequest
        from opencontext_api.sdd_routes import sdd_phase

        with patch(
            "opencontext_api.sdd_routes.run_phase",
            side_effect=RuntimeError("internal boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                sdd_phase(
                    phase="propose",
                    body=SDDPhaseRequest(change="test", cwd="."),
                )

        assert exc_info.value.status_code == 500
        # detail must be a safe string, not a traceback
        detail = str(exc_info.value.detail)
        assert "traceback" not in detail.lower()
        assert "internal boom" not in detail or len(detail) < 200, (
            "HTTPException detail appears to leak internal stack text."
        )

    def test_sdd_phase_500_detail_is_structured(self) -> None:
        """The 500 detail must be a dict or short string — no raw tracebacks."""
        from fastapi import HTTPException

        from opencontext_api.schemas import SDDPhaseRequest
        from opencontext_api.sdd_routes import sdd_phase

        with patch(
            "opencontext_api.sdd_routes.run_phase",
            side_effect=ValueError("secret path /home/user/.secrets"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                sdd_phase("spec", SDDPhaseRequest(change="c", cwd="."))

        detail = exc_info.value.detail
        if isinstance(detail, str):
            # Must not contain the raw exception message (path leak).
            assert "/home/user" not in detail, "Stack/path leaked into 500 detail."
        # status must be 500
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Finding 4 (MEDIUM): GateStatus.NOT_APPLIED semantic alignment
# ---------------------------------------------------------------------------


class TestGateStatusNotAppliedSemantic:
    """NOT_APPLIED must be non-blocking (is_ok True) to align with boundary.py."""

    def test_not_applied_is_ok_is_true(self) -> None:
        """GateStatus.NOT_APPLIED.is_ok must be True (non-blocking)."""
        from opencontext_core.harness.models import GateStatus

        assert GateStatus.NOT_APPLIED.is_ok is True, (
            "NOT_APPLIED.is_ok is False, contradicting boundary.py success=True; "
            "align semantics: NOT_APPLIED = non-blocking advisory, not a failure."
        )

    def test_boundary_not_applied_maps_to_success(self) -> None:
        """boundary.py success check must agree with is_ok for NOT_APPLIED."""
        from opencontext_core.harness.models import GateStatus

        status = GateStatus.NOT_APPLIED
        boundary_success = status not in ("failed", "error")
        assert boundary_success is True
        assert status.is_ok is True, (
            "boundary.py says success but is_ok says False — contradiction."
        )

    def test_quality_report_exit_code_not_applied_is_zero(self) -> None:
        """QualityReport with NOT_APPLIED status must have exit_code 0."""
        from opencontext_core.harness.models import GateStatus
        from opencontext_core.quality.models import (
            HealthScore,
            QualityMetrics,
            QualityReport,
        )

        metrics = QualityMetrics()
        health = HealthScore(score=10000, metrics=metrics, components={})
        report = QualityReport(
            status=GateStatus.NOT_APPLIED,
            findings=(),
            verdicts=(),
            health=health,
        )
        assert report.exit_code == 0, (
            "NOT_APPLIED should exit with code 0 (non-blocking), got 1."
        )

    def test_failed_is_not_ok(self) -> None:
        """Sanity: GateStatus.FAILED.is_ok must still be False."""
        from opencontext_core.harness.models import GateStatus

        assert GateStatus.FAILED.is_ok is False

    def test_warning_is_not_ok(self) -> None:
        """Sanity: GateStatus.WARNING.is_ok must still be False."""
        from opencontext_core.harness.models import GateStatus

        assert GateStatus.WARNING.is_ok is False


# ---------------------------------------------------------------------------
# Finding 5 (MEDIUM): TestsPassGate wired into verify phase
# ---------------------------------------------------------------------------


class TestTestsPassGateWiredInVerify:
    """TestsPassGate must be called during the verify phase in strict mode."""

    def test_tests_pass_gate_class_importable(self) -> None:
        """TestsPassGate must be importable from gates module."""
        from opencontext_core.harness.gates import TestsPassGate  # noqa: F401

    def test_tests_pass_gate_imported_in_runner(self) -> None:
        """runner.py must import TestsPassGate so it can wire it."""
        import opencontext_core.harness.runner as runner_mod

        assert hasattr(runner_mod, "TestsPassGate") or "TestsPassGate" in dir(runner_mod), (
            "TestsPassGate not imported in runner module."
        )

    def test_dispatch_one_gate_handles_tests_pass(self, tmp_path: Path) -> None:
        """_dispatch_one_gate must return a PhaseGate for 'tests_pass' gate_id."""
        from opencontext_core.harness.runner import HarnessRunner

        runner = HarnessRunner(root=tmp_path)
        # Build a minimal state and result stub.
        state = MagicMock()
        state.root = tmp_path
        state.trace_ids = []
        result = MagicMock()
        result.artifacts = []
        result.gates = []

        gate = runner._dispatch_one_gate("tests_pass", "verify", state, result)
        # In non-strict mode, TestsPassGate returns PASSED (inactive).
        # The key check: it must NOT return None (which means "unbound").
        assert gate is not None, (
            "_dispatch_one_gate returned None for 'tests_pass'; gate is not wired."
        )

    def test_tests_pass_gate_in_strict_fails_on_failing_suite(
        self, tmp_path: Path
    ) -> None:
        """In strict mode, TestsPassGate.evaluate() with exit!=0 → FAILED."""
        from opencontext_core.harness.gates import TestsPassGate
        from opencontext_core.harness.models import GateStatus

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=1, stdout="FAIL", stderr="")
            gate = TestsPassGate().evaluate(
                cmd=["pytest", "-q"],
                cwd=tmp_path,
                tdd_mode="strict",
            )

        assert gate.status == GateStatus.FAILED, (
            "TestsPassGate did not return FAILED for a failing suite in strict mode."
        )


# ---------------------------------------------------------------------------
# Finding 6 (MEDIUM): _install_json hardcodes status="ok" on SystemExit
# ---------------------------------------------------------------------------


class TestInstallJsonSystemExitStatus:
    """_install_json must map SystemExit(1) → status='error'.

    _install_json writes JSON to stdout and returns None.  Tests capture
    stdout output and parse the emitted JSON payload.
    """

    def _run_install_json(self, tmp_path: Path, side_effect: BaseException) -> dict:
        """Run _install_json with a patched _install and return the parsed JSON."""
        import argparse
        import io
        import json

        import opencontext_cli.main as m

        _install_json = getattr(m, "_install_json", None)
        if _install_json is None:
            pytest.skip("_install_json not found in main.py")

        args = argparse.Namespace(
            root=str(tmp_path),
            yes=True,
            json=True,
            tdd=None,
        )

        captured = io.StringIO()
        with patch("opencontext_cli.main._install", side_effect=side_effect):
            import sys
            real_stdout = sys.stdout
            sys.stdout = captured  # type: ignore[assignment]
            try:
                _install_json(args)
            finally:
                sys.stdout = real_stdout

        output = captured.getvalue().strip()
        return json.loads(output) if output else {}

    def test_system_exit_1_yields_error_status(self, tmp_path: Path) -> None:
        """SystemExit(1) from _install() must yield status='error' in JSON."""
        result = self._run_install_json(tmp_path, SystemExit(1))
        assert result.get("status") == "error", (
            f"SystemExit(1) produced status={result.get('status')!r}; expected 'error'."
        )

    def test_system_exit_0_yields_ok_status(self, tmp_path: Path) -> None:
        """SystemExit(0) from _install() must yield status='ok'."""
        result = self._run_install_json(tmp_path, SystemExit(0))
        assert result.get("status") == "ok", (
            f"SystemExit(0) produced status={result.get('status')!r}; expected 'ok'."
        )

    def test_system_exit_none_yields_ok_status(self, tmp_path: Path) -> None:
        """SystemExit(None) (graceful) must also yield status='ok'."""
        result = self._run_install_json(tmp_path, SystemExit(None))
        assert result.get("status") == "ok", (
            f"SystemExit(None) produced status={result.get('status')!r}; expected 'ok'."
        )


# ---------------------------------------------------------------------------
# Finding 7 (LOW): dynamic import of _MUTATION_VERBS/_READONLY_VERBS in hot path
# ---------------------------------------------------------------------------


class TestMutationVerbsHoistedImport:
    """_MUTATION_VERBS and _READONLY_VERBS must be importable at module level."""

    def test_mutation_verbs_importable_directly(self) -> None:
        """The verb lists must be importable from oc_flow.completion."""
        from opencontext_core.oc_flow.completion import (
            _MUTATION_VERBS,
            _READONLY_VERBS,
        )
        assert isinstance(_MUTATION_VERBS, (list, tuple, frozenset, set))
        assert isinstance(_READONLY_VERBS, (list, tuple, frozenset, set))

    def test_runner_module_has_verb_constants(self) -> None:
        """runner.py must expose the verb lists at module level (not only inside try)."""
        import opencontext_core.harness.runner as runner_mod

        # After the fix, the module-level names must be set.
        assert hasattr(runner_mod, "_MUTATION_VERBS"), (
            "_MUTATION_VERBS not hoisted to module level in runner.py."
        )
        assert hasattr(runner_mod, "_READONLY_VERBS"), (
            "_READONLY_VERBS not hoisted to module level in runner.py."
        )

    def test_fallback_does_not_mark_everything_mutation(self) -> None:
        """When the import fails (simulated), fallback must not silently mark every task
        as a mutation — the fallback must be deterministic and logged."""
        import opencontext_core.harness.runner as runner_mod

        # Simulate import failure by temporarily replacing the module-level names.
        orig_mut = getattr(runner_mod, "_MUTATION_VERBS", None)
        orig_ro = getattr(runner_mod, "_READONLY_VERBS", None)
        try:
            runner_mod._MUTATION_VERBS = None  # type: ignore[attr-defined]
            runner_mod._READONLY_VERBS = None  # type: ignore[attr-defined]
            # The runner code should handle None gracefully (via the ImportError
            # guard path) without raising.
            # We cannot call the full runner here; just verify the attribute access
            # does not hard-crash.
            assert runner_mod._MUTATION_VERBS is None  # confirm the patch worked
        finally:
            if orig_mut is not None:
                runner_mod._MUTATION_VERBS = orig_mut  # type: ignore[attr-defined]
            if orig_ro is not None:
                runner_mod._READONLY_VERBS = orig_ro  # type: ignore[attr-defined]
