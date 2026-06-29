"""ImplementationSlice model + decomposition of a mapped intent into slices.

``decompose`` groups requirement ids into ordered ``ImplementationSlice``s such
that every (non-blank) requirement lands in exactly one slice. Decomposition is
deterministic and offline.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.planning.intent import IntentRecord
from opencontext_core.planning.risk import RiskAssessment

# Group-key keyword -> (task_type, risk_level) hint for inferred classification.
_TASK_TYPE_HINTS: dict[str, tuple[str, str]] = {
    "security": ("security", "high"),
    "policy": ("security", "high"),
    "migration": ("migration", "medium"),
    "perf": ("performance", "high"),
    "benchmark": ("performance", "medium"),
    "doc": ("documentation", "low"),
    "config": ("configuration", "low"),
    "test": ("test", "low"),
    "fix": ("bugfix", "low"),
    "refactor": ("refactor", "medium"),
}


class ImplementationSlice(BaseModel):
    """A typed unit of implementation work spanning one or more requirements."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.slice.v1"
    slice_id: str
    title: str
    requirement_ids: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    task_type: str = "feature"
    risk_level: str = "medium"
    risk: RiskAssessment | None = None
    estimate: dict[str, Any] = Field(default_factory=dict)
    recommended_workflow: str | None = None


def _group_key(requirement_id: str) -> str:
    """Derive the grouping key for a requirement id (token before the first ``-``)."""
    cleaned = requirement_id.strip()
    return cleaned.split("-", 1)[0] if "-" in cleaned else cleaned


def _classify_group(key: str) -> tuple[str, str]:
    lowered = key.lower()
    for needle, hint in _TASK_TYPE_HINTS.items():
        if needle in lowered:
            return hint
    return ("feature", "medium")


def decompose(
    intent: IntentRecord, requirements: Sequence[str]
) -> list[ImplementationSlice]:
    """Decompose *requirements* into an ordered list of ``ImplementationSlice``s.

    Blank requirement ids are dropped (so ``build`` can surface them as orphans),
    duplicates collapse, and every remaining requirement appears in exactly one
    slice. Groups are emitted in first-seen order for determinism.
    """
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for raw in requirements:
        requirement_id = raw.strip()
        if not requirement_id:
            continue
        key = _group_key(requirement_id)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        if requirement_id not in grouped[key]:
            grouped[key].append(requirement_id)

    slices: list[ImplementationSlice] = []
    for index, key in enumerate(order, start=1):
        task_type, risk_level = _classify_group(key)
        slices.append(
            ImplementationSlice(
                slice_id=f"slice-{index:03d}-{key.lower()}",
                title=f"Implement {key}",
                requirement_ids=grouped[key],
                task_type=task_type,
                risk_level=risk_level,
            )
        )
    return slices


__all__ = ["ImplementationSlice", "decompose"]
