"""Generic, gate-aware state machine (SPEC RC-007).

``StateMachine.evaluate`` returns a ``TransitionDecision`` for every proposed
node transition; no transition occurs without one. It is workflow-neutral: the
required gates come from the ``transition_condition`` and their satisfaction
from the ``runtime_context``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TransitionDecision(BaseModel):
    """The verdict for one proposed transition (book §10.2)."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str = ""
    required_gates: list[str] = Field(default_factory=list)
    failed_gates: list[str] = Field(default_factory=list)
    next_node: str | None = None


class StateMachine:
    """Validates transitions between workflow nodes (book §10.1)."""

    def evaluate(
        self,
        *,
        current_node: str | None,
        target_node: str | None,
        workflow_definition: Any = None,
        transition_condition: Mapping[str, Any] | None = None,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> TransitionDecision:
        """Decide whether ``current_node`` may transition to ``target_node``.

        ``transition_condition`` may carry ``required_gates: list[str]``.
        ``runtime_context`` may carry ``gates: dict[str, bool]`` recording which
        gates are currently satisfied. A transition is allowed only when a
        target node is supplied and every required gate is satisfied.
        """
        condition = dict(transition_condition or {})
        context = dict(runtime_context or {})
        required_gates = [str(g) for g in condition.get("required_gates", [])]
        gate_states = dict(context.get("gates", {}))
        failed_gates = [g for g in required_gates if not bool(gate_states.get(g, False))]

        if not target_node:
            return TransitionDecision(
                allowed=False,
                reason="no target node supplied",
                required_gates=required_gates,
                failed_gates=failed_gates,
                next_node=None,
            )
        if failed_gates:
            return TransitionDecision(
                allowed=False,
                reason=f"unmet required gates: {', '.join(failed_gates)}",
                required_gates=required_gates,
                failed_gates=failed_gates,
                next_node=None,
            )
        return TransitionDecision(
            allowed=True,
            reason="all required gates satisfied",
            required_gates=required_gates,
            failed_gates=[],
            next_node=target_node,
        )
