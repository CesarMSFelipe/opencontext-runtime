"""Shared workflow selector (B6 / AVH-013).

ONE selection policy, consumed by BOTH ``oc_flow.runner.select_workflow`` (which
backs ``run --workflow auto``) and ``runtime_intelligence.simulator``. Before this
seam existed the two surfaces routed independently and disagreed — the audit saw
``simulate "Redesign public API and migrate schema"`` choose oc-flow while
``run --workflow auto`` chose SDD. Routing through one function makes disagreement
structurally impossible.

Routing is on task CLASS and RISK, never on ``requires_mutation`` alone (a localized
bugfix mutates but still belongs to OC Flow): architecture / schema / public-API /
migration / security / breaking → SDD; everything else (localized bugfix, lint,
small refactor, docs) → OC Flow, with high/critical risk also escalating to SDD.

Layering (doc 58): L5 (context), importing only the sibling L5 planning classifiers
downward — both the L9 runner and the L10 simulator import it downward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from opencontext_core.context.planning.classifier import TaskClassifier
from opencontext_core.context.planning.risk import RiskClassifier

# Task classes that demand the formal SDD workflow regardless of risk level. These
# mirror the classifier's task_type vocabulary plus forward-compatible aliases
# (``schema`` / ``public_api`` / ``breaking``) other classifiers may emit.
_SDD_TASK_TYPES: frozenset[str] = frozenset(
    {"architecture", "schema", "public_api", "migration", "security", "breaking"}
)


@dataclass(frozen=True)
class WorkflowSelection:
    """An explainable workflow-selection receipt (chosen + why)."""

    workflow: str  # "sdd" | "oc-flow"
    reason: str
    signals: dict[str, Any] = field(default_factory=dict)


def select_workflow(
    task: str,
    *,
    classifier: TaskClassifier | None = None,
    risk: RiskClassifier | None = None,
) -> WorkflowSelection:
    """Resolve ``task`` to ``sdd`` or ``oc-flow`` with an explainable receipt.

    SDD wins when the task class is broad/high-stakes (architecture / schema /
    public-API / migration / security / breaking) OR the risk level is high or
    critical. Otherwise OC Flow — the fast operational default — is chosen.
    """
    classification = (classifier or TaskClassifier()).classify(task)
    tier = (risk or RiskClassifier()).classify(classification.task_type, classification.risk_level)

    high_risk = classification.risk_level in ("high", "critical")
    sdd_class = classification.task_type in _SDD_TASK_TYPES
    workflow = "sdd" if (high_risk or sdd_class) else "oc-flow"

    reason = (
        f"task_type={classification.task_type}, risk={classification.risk_level} "
        f"-> {workflow}"
        + (" (broad/high-stakes class)" if sdd_class else "")
        + (" (high risk)" if high_risk and not sdd_class else "")
    )
    return WorkflowSelection(
        workflow=workflow,
        reason=reason,
        signals={
            "task_type": classification.task_type,
            "risk_level": classification.risk_level,
            "retrieval_tier": tier,
            "requires_mutation": classification.requires_mutation,
            "confidence": round(classification.confidence, 3),
        },
    )


__all__ = ["WorkflowSelection", "select_workflow"]
