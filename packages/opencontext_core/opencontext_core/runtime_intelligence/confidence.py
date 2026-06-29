"""Confidence Engine (book §8/§9) — 8 evidence-derived dimensions + action.

System-level confidence is NOT model certainty; it is evidence-based confidence
across the eight runtime dimensions. Each dimension derives from a real signal
(pack coverage, the harness :class:`~opencontext_core.harness.gates.ConfidenceGate`
score, memory hit-rate, policy-violation rate, gate pass/fail). When a signal is
absent the dimension falls back to a conservative default that is DISCLOSED in
``evidence_refs`` (``default:<dim>=no_signal``) — never silently invented
(design DEC-4).

The engine maps the overall score to exactly one bounded action (book §9). It
only recommends — the Runtime governs the final decision (invariant §23.1).
"""

from __future__ import annotations

from dataclasses import dataclass

from opencontext_core.models.intelligence import (
    CONFIDENCE_DIMENSIONS,
    ConfidenceAction,
    ConfidenceReport,
)

# Default thresholds (book §18). The Confidence Engine recommends; the Runtime
# enforces. ``switch_workflow_below`` < ``ask_below`` < ``deep_mode_below``.
DEFAULT_SWITCH_WORKFLOW_BELOW = 0.55
DEFAULT_ASK_BELOW = 0.65
DEFAULT_DEEP_MODE_BELOW = 0.75
# Below this floor the situation is escalated regardless of the band above.
DEFAULT_ESCALATE_BELOW = 0.30
# A critically low single-axis signal short-circuits to a targeted action.
_CRITICAL_AXIS = 0.40

_DEFAULT_DIM = 0.5  # conservative, disclosed fallback for an absent signal.


@dataclass
class ConfidenceSignals:
    """Real evidence signals feeding the eight dimensions (all optional).

    A ``None`` value means "no signal for this dimension"; the engine then uses a
    conservative default and records the substitution in ``evidence_refs``.
    """

    intent_confidence: float | None = None  # classifier confidence in the task type
    context_coverage: float | None = None  # ContextScore / pack expected-source coverage
    plan_confidence: float | None = None  # harness ConfidenceGate score for the plan
    mutation_confidence: float | None = None  # mutation gate status / risk inverse
    inspection_confidence: float | None = None  # inspection gate / test pass evidence
    memory_hit_rate: float | None = None  # memory retrieval hit-rate
    policy_violation_rate: float | None = None  # security: rate of policy violations [0,1]


@dataclass
class ConfidenceThresholds:
    switch_workflow_below: float = DEFAULT_SWITCH_WORKFLOW_BELOW
    ask_below: float = DEFAULT_ASK_BELOW
    deep_mode_below: float = DEFAULT_DEEP_MODE_BELOW
    escalate_below: float = DEFAULT_ESCALATE_BELOW


class ConfidenceEngine:
    """Compute a :class:`ConfidenceReport` and recommend a bounded action."""

    def __init__(self, thresholds: ConfidenceThresholds | None = None) -> None:
        self.thresholds = thresholds or ConfidenceThresholds()

    def report(
        self,
        *,
        session_id: str,
        run_id: str,
        workflow: str,
        signals: ConfidenceSignals,
    ) -> ConfidenceReport:
        """Build the 8-dimension report and map ``overall`` to one action."""
        evidence: list[str] = []

        def dim(name: str, value: float | None) -> float:
            if value is None:
                evidence.append(f"default:{name}=no_signal")
                return _DEFAULT_DIM
            evidence.append(f"signal:{name}={round(float(value), 3)}")
            return _clamp(float(value))

        security = (
            dim("security", None)
            if signals.policy_violation_rate is None
            else _clamp(1.0 - signals.policy_violation_rate)
        )
        if signals.policy_violation_rate is not None:
            evidence.append(f"signal:security={round(security, 3)}")

        dims = {
            "intent": dim("intent", signals.intent_confidence),
            "context": dim("context", signals.context_coverage),
            "plan": dim("plan", signals.plan_confidence),
            "mutation": dim("mutation", signals.mutation_confidence),
            "inspection": dim("inspection", signals.inspection_confidence),
            "memory": dim("memory", signals.memory_hit_rate),
            "security": security,
        }
        overall = round(sum(dims.values()) / len(dims), 4)
        dims["overall"] = overall  # 8th key (book §8).

        action = self._action(overall, dims)
        return ConfidenceReport(
            session_id=session_id,
            run_id=run_id,
            workflow=workflow,
            dimensions=dims,
            overall=overall,
            threshold=self.thresholds.ask_below,
            recommended_action=action,
            evidence_refs=evidence,
        )

    def _action(self, overall: float, dims: dict[str, float]) -> ConfidenceAction:
        """Map overall (and a couple of critical axes) to one bounded action."""
        t = self.thresholds
        # Targeted short-circuits for a critically low single axis.
        if dims.get("security", 1.0) < _CRITICAL_AXIS:
            return "require_approval"
        if overall < t.escalate_below:
            return "escalate"
        if overall < t.switch_workflow_below:
            return "switch_workflow"
        if overall < t.ask_below:
            return "ask"
        if overall < t.deep_mode_below:
            return "deep_mode"
        if dims.get("context", 1.0) < t.deep_mode_below:
            return "retrieve_deeper"
        return "continue"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# Re-export the dimension vocabulary for callers/tests.
DIMENSIONS = CONFIDENCE_DIMENSIONS

__all__ = [
    "DEFAULT_ASK_BELOW",
    "DEFAULT_DEEP_MODE_BELOW",
    "DEFAULT_SWITCH_WORKFLOW_BELOW",
    "DIMENSIONS",
    "ConfidenceEngine",
    "ConfidenceSignals",
    "ConfidenceThresholds",
]
