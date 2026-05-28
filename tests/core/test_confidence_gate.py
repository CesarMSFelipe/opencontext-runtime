"""Tests for ConfidenceGate."""

from __future__ import annotations

from opencontext_core.harness.gates import ConfidenceGate, GateStatus, PhaseGate


class TestConfidenceGate:
    """ConfidenceGate evaluation tests."""

    def test_passes_by_default(self) -> None:
        """With default threshold and no prior data, should pass."""
        gate = ConfidenceGate()
        result = gate.evaluate(phase="explore")
        assert result.status == GateStatus.PASSED
        assert result.id == "confidence"

    def test_fails_when_below_threshold(self) -> None:
        """Threshold of 0.99 should fail for any phase."""
        gate = ConfidenceGate()
        result = gate.evaluate(phase="explore", threshold=0.99)
        assert result.status == GateStatus.FAILED
        assert result.metadata["confidence_score"] < 0.99

    def test_previous_failures_lower_confidence(self) -> None:
        """Prior failed gates should reduce confidence."""
        gate = ConfidenceGate()
        failed_prev = [
            PhaseGate(id="prev", phase="explore", status=GateStatus.FAILED),
        ]
        result = gate.evaluate(
            phase="apply",
            threshold=0.6,
            previous_gates=failed_prev,
        )
        assert result.status == GateStatus.FAILED

    def test_previous_successes_raise_confidence(self) -> None:
        """Prior passed gates should increase confidence."""
        gate = ConfidenceGate()
        passed_prev = [
            PhaseGate(id="prev1", phase="explore", status=GateStatus.PASSED),
            PhaseGate(id="prev2", phase="propose", status=GateStatus.PASSED),
        ]
        result = gate.evaluate(
            phase="apply",
            threshold=0.6,
            previous_gates=passed_prev,
        )
        # With all previous passed and no test coverage data,
        # score = 0.2 * (1-0.8) + 0.5 * 1.0 + 0.3 * 0.5 = 0.04 + 0.5 + 0.15 = 0.69
        assert result.status == GateStatus.PASSED

    def test_high_test_coverage_helps(self) -> None:
        """High test coverage should boost confidence."""
        gate = ConfidenceGate()
        result = gate.evaluate(
            phase="apply",
            threshold=0.5,
            test_coverage=0.9,
            previous_gates=[
                PhaseGate(id="prev", phase="explore", status=GateStatus.PASSED),
            ],
        )
        # score = 0.2 * (1-0.8) + 0.5 * 1.0 + 0.3 * 0.9 = 0.04 + 0.5 + 0.27 = 0.81
        assert result.status == GateStatus.PASSED
        assert result.metadata["confidence_score"] >= 0.8

    def test_low_test_coverage_hurts(self) -> None:
        """Low test coverage with no prior data should still pass moderate threshold."""
        gate = ConfidenceGate()
        result = gate.evaluate(
            phase="explore",
            threshold=0.5,
            test_coverage=0.1,
        )
        # score = 0.2 * (1-0.2) + 0.5 * 0.5 + 0.3 * 0.1 = 0.16 + 0.25 + 0.03 = 0.44
        assert result.status == GateStatus.FAILED

    def test_metadata_includes_details(self) -> None:
        """Result metadata should contain details list."""
        gate = ConfidenceGate()
        result = gate.evaluate(phase="design", threshold=0.5, test_coverage=0.7)
        assert "details" in result.metadata
        assert len(result.metadata["details"]) >= 3
        assert any("coverage=70%" in d for d in result.metadata["details"])

    def test_phase_complexity_mapping(self) -> None:
        """Verify complexity is lower for simple phases, higher for complex."""
        gate = ConfidenceGate()
        explore = gate.evaluate(phase="explore")
        apply_phase = gate.evaluate(phase="apply")
        # apply has higher complexity (0.8) so lower factor -> lower score
        assert explore.metadata["confidence_score"] > apply_phase.metadata["confidence_score"]

    def test_no_previous_gates_is_neutral(self) -> None:
        """When no prior gates, factor defaults to 0.5."""
        gate = ConfidenceGate()
        result = gate.evaluate(phase="tasks", threshold=0.0)  # threshold 0 always passes
        # score = 0.2 * (1-0.3) + 0.5 * 0.5 + 0.3 * 0.5 = 0.14 + 0.25 + 0.15 = 0.54
        score = result.metadata["confidence_score"]
        assert 0.5 <= score <= 0.6


class TestConfidenceGateHarnessIntegration:
    """Test that ConfidenceGate is wired into the harness run loop."""

    def test_confidence_threshold_in_phase_config(self) -> None:
        """Default apply phase should have confidence_threshold=0.4."""
        from opencontext_core.harness.config import HarnessConfig

        config = HarnessConfig()
        assert config.phases["apply"].confidence_threshold == 0.4
        assert config.phases["verify"].confidence_threshold == 0.3

    def test_confidence_gate_blocked_in_strict_mode(self, tmp_path, monkeypatch) -> None:
        """In strict mode, a blocked confidence gate should stop the run."""
        from opencontext_core.harness.config import HarnessConfig, PhaseConfig
        from opencontext_core.harness.models import BudgetMode
        from opencontext_core.harness.runner import HarnessRunner

        # Create a config with high threshold
        config = HarnessConfig()
        config.phases["apply"] = PhaseConfig(
            budget_tokens=12000,
            confidence_threshold=0.99,  # impossible to pass
            gates=[],
        )

        runner = HarnessRunner(root=tmp_path, config=config)
        result = runner.run(
            workflow="apply-only",
            task="test task",
            budget_mode=BudgetMode.STRICT,
        )

        # The run should be blocked at apply phase
        assert result.status == GateStatus.FAILED
        # Should have a confidence gate failure
        confidence_gates = [g for g in result.gates if g.id == "confidence"]
        assert len(confidence_gates) >= 1
        assert any("blocked" in w.lower() for w in result.warnings)
