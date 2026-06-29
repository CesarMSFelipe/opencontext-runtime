"""Per-slice cost/effort estimate + recommended workflow (SDD vs OC Flow).

Both helpers are deterministic functions of a slice's risk level and scope. A
localized, low-risk slice is routed to ``oc-flow``; higher-risk or wider-scope
slices are routed to the formal ``sdd`` workflow.
"""

from __future__ import annotations

from math import ceil
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opencontext_core.planning.decomposition import ImplementationSlice

# Approximate lines-of-code budget per requirement, keyed by risk level.
_LOC_PER_REQUIREMENT: dict[str, int] = {
    "cheap": 60,
    "precise": 140,
    "critical": 240,
}
_REVIEW_BUDGET = 400  # one review unit per ~400 changed lines (repo convention)


def _level(slice: ImplementationSlice) -> str:
    return slice.risk.level if slice.risk is not None else "precise"


def estimate(slice: ImplementationSlice) -> dict[str, Any]:
    """Return a cost/effort estimate dict for *slice*."""
    scope = max(1, len(slice.requirement_ids))
    level = _level(slice)
    loc = scope * _LOC_PER_REQUIREMENT.get(level, _LOC_PER_REQUIREMENT["precise"])
    review_units = max(1, ceil(loc / _REVIEW_BUDGET))
    if loc <= 200:
        effort = "small"
    elif loc <= 600:
        effort = "medium"
    else:
        effort = "large"
    return {
        "effort": effort,
        "loc": loc,
        "review_units": review_units,
        "requirement_count": scope,
        "risk_level": level,
    }


def recommend_workflow(slice: ImplementationSlice) -> str:
    """Recommend ``"oc-flow"`` for localized low-risk slices, else ``"sdd"``."""
    level = _level(slice)
    scope = len(slice.requirement_ids)
    if level == "cheap" and scope <= 1:
        return "oc-flow"
    return "sdd"


__all__ = ["estimate", "recommend_workflow"]
