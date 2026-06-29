"""The six built-in execution strategies (CP-009).

A strategy is a named intent (``fast``/``cheap``/``careful``/``enterprise``/
``research``/``local_first``) that maps onto one of the five built-in execution
profiles. Strategies are declared as data so they stay inspectable and a plugin
can register more later.

Layering (doc 58): L3. Imports only the sibling ``profiles.definition`` models.
"""

from __future__ import annotations

from opencontext_core.profiles.definition import ExecutionProfileStrategy

# The six strategies, each mapped onto a built-in profile id from
# ``capabilities.registry.BUILTIN_PROFILES`` (CP-009).
BUILTIN_STRATEGIES: dict[str, ExecutionProfileStrategy] = {
    "fast": ExecutionProfileStrategy(
        id="fast",
        profile_id="performance",
        description="Lowest latency to a result: largest budget, remote-first.",
    ),
    "cheap": ExecutionProfileStrategy(
        id="cheap",
        profile_id="low-cost",
        description="Lowest spend: small budget, advisory harness, local-first.",
    ),
    "careful": ExecutionProfileStrategy(
        id="careful",
        profile_id="enterprise",
        description="Highest rigor: blocking harness, policy routing, more retries.",
    ),
    "enterprise": ExecutionProfileStrategy(
        id="enterprise",
        profile_id="enterprise",
        description="Governed posture for regulated work (maps to the enterprise profile).",
    ),
    "research": ExecutionProfileStrategy(
        id="research",
        profile_id="research",
        description="Exploration posture: large budget, strong remote models.",
    ),
    "local_first": ExecutionProfileStrategy(
        id="local_first",
        profile_id="low-cost",
        description="Prefer a local backend before any remote provider.",
    ),
}


def builtin_strategy_ids() -> list[str]:
    """Return the ids of the built-in strategies in declaration order."""
    return list(BUILTIN_STRATEGIES)


def get_strategy(strategy_id: str) -> ExecutionProfileStrategy | None:
    """Return the built-in strategy for ``strategy_id`` or ``None`` when unknown."""
    return BUILTIN_STRATEGIES.get(strategy_id)
