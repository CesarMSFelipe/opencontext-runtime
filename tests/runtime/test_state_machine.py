"""Tests for the generic state machine (SPEC RC-007)."""

from __future__ import annotations

from opencontext_core.runtime.state_machine import StateMachine, TransitionDecision


class TestEvaluate:
    def test_disallowed_when_required_gate_unmet(self) -> None:
        sm = StateMachine()
        decision = sm.evaluate(
            current_node="spec",
            target_node="apply",
            transition_condition={"required_gates": ["tests_pass"]},
            runtime_context={"gates": {"tests_pass": False}},
        )
        assert isinstance(decision, TransitionDecision)
        assert decision.allowed is False
        assert decision.failed_gates == ["tests_pass"]
        assert decision.next_node is None

    def test_allowed_when_gates_satisfied(self) -> None:
        sm = StateMachine()
        decision = sm.evaluate(
            current_node="spec",
            target_node="apply",
            transition_condition={"required_gates": ["tests_pass"]},
            runtime_context={"gates": {"tests_pass": True}},
        )
        assert decision.allowed is True
        assert decision.failed_gates == []
        assert decision.next_node == "apply"

    def test_disallowed_without_target(self) -> None:
        sm = StateMachine()
        decision = sm.evaluate(current_node="archive", target_node=None, runtime_context={})
        assert decision.allowed is False
        assert decision.next_node is None
