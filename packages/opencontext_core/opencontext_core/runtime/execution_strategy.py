"""ExecutionStrategy — the unified per-run/node execution profile (RB-006).

Today the knobs are split across ``agentic/config.py BudgetMode``,
``harness/models.py BudgetMode`` and ``economy/strategy.py EconomyDecision``,
with no single resolved object. :class:`ExecutionStrategy` unifies budget mode,
retry budget, harness strictness, and provider-routing preference; the Brain
emits it as an ``execution_profile`` decision.

The mapping is deterministic given a profile name: ``enterprise`` is strictly
tighter (budget/harness/retry) than ``low-cost``, and the difference is recorded
in ``notes`` (RB-006 scenario).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

HarnessStrictness = Literal["off", "warn", "strict"]


class ExecutionStrategy(BaseModel):
    """A resolved execution strategy for a run/node."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.execution_strategy.v1"
    profile: str
    budget_mode: str
    retry_budget: int = 1
    harness_strictness: HarnessStrictness = "warn"
    provider_routing: str = "default"
    notes: list[str] = Field(default_factory=list)


# Profile -> resolved knobs. Ordering of strictness (loosest..strictest):
#   low-cost < performance < balanced < research < enterprise
# Kept as plain data so resolution is a deterministic lookup, not branching.
_PROFILES: dict[str, dict[str, Any]] = {
    "low-cost": {
        "budget_mode": "off",
        "retry_budget": 0,
        "harness_strictness": "off",
        "provider_routing": "local_first",
    },
    "performance": {
        "budget_mode": "warn",
        "retry_budget": 1,
        "harness_strictness": "warn",
        "provider_routing": "default",
    },
    "balanced": {
        "budget_mode": "warn",
        "retry_budget": 1,
        "harness_strictness": "warn",
        "provider_routing": "default",
    },
    "research": {
        "budget_mode": "adaptive",
        "retry_budget": 2,
        "harness_strictness": "warn",
        "provider_routing": "careful",
    },
    "enterprise": {
        "budget_mode": "strict",
        "retry_budget": 3,
        "harness_strictness": "strict",
        "provider_routing": "careful",
    },
}

_DEFAULT_PROFILE = "balanced"


def resolve_strategy(profile: str, *, economy: Any = None) -> ExecutionStrategy:
    """Resolve an :class:`ExecutionStrategy` for *profile*.

    *economy* may be an ``economy/strategy.py EconomyDecision`` (or any object
    exposing ``compact_handoff`` / ``include_code_snippets`` /
    ``max_handoff_tokens``); when supplied its effect is folded into ``notes``
    so the economy contribution stays inspectable rather than silently merged.
    """
    key = profile if profile in _PROFILES else _DEFAULT_PROFILE
    knobs = _PROFILES[key]
    notes = [
        f"profile '{key}': budget_mode={knobs['budget_mode']}, "
        f"harness_strictness={knobs['harness_strictness']}, "
        f"retry_budget={knobs['retry_budget']}, "
        f"provider_routing={knobs['provider_routing']}"
    ]
    if key != profile:
        notes.append(f"unknown profile '{profile}' -> defaulted to '{key}'")
    if economy is not None:
        cap = getattr(economy, "max_handoff_tokens", None)
        compact = getattr(economy, "compact_handoff", None)
        notes.append(f"economy: compact_handoff={compact}, max_handoff_tokens={cap}")

    return ExecutionStrategy(
        profile=key,
        budget_mode=str(knobs["budget_mode"]),
        retry_budget=int(knobs["retry_budget"]),
        harness_strictness=knobs["harness_strictness"],
        provider_routing=str(knobs["provider_routing"]),
        notes=notes,
    )
