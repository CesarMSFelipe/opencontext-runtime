"""Program-scoped ``RiskAssessment`` — a thin wrapper over ``RiskClassifier``.

This module deliberately reuses the shipped, retrieval-scoped
``opencontext_core.context.planning.risk.RiskClassifier`` instead of introducing a
second risk taxonomy. ``RiskClassifier`` is re-exported so callers (and the
foundation-reuse test) can confirm there is exactly one classifier.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

# Reuse, do not duplicate: the single risk classifier lives in context/planning.
from opencontext_core.context.planning.risk import RiskClassifier

if TYPE_CHECKING:
    from opencontext_core.planning.decomposition import ImplementationSlice

_MITIGATIONS: dict[str, list[str]] = {
    "cheap": ["single-reviewer sign-off"],
    "precise": ["focused tests on touched requirements", "peer review"],
    "critical": [
        "design review before apply",
        "full regression + security review",
        "staged rollout with rollback plan",
    ],
}


class RiskAssessment(BaseModel):
    """Per-slice, program-scoped risk record derived via ``RiskClassifier``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.risk.v1"
    level: str
    factors: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)


def assess(slice: ImplementationSlice, *, task_type: str, risk_level: str) -> RiskAssessment:
    """Build a ``RiskAssessment`` for *slice*, deriving ``level`` via ``RiskClassifier``."""
    level = RiskClassifier().classify(task_type, risk_level)
    factors = [
        f"task_type={task_type}",
        f"risk_level={risk_level}",
        f"requirements={len(slice.requirement_ids)}",
    ]
    mitigations = list(_MITIGATIONS.get(level, _MITIGATIONS["precise"]))
    return RiskAssessment(level=level, factors=factors, mitigations=mitigations)


__all__ = ["RiskAssessment", "RiskClassifier", "assess"]
