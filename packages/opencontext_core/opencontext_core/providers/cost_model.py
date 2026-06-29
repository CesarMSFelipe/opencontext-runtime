"""Provider cost model (book §25 "Cost Tracking"; PG-CONV provider cost model).

Per-provider token pricing used to derive ``estimated_cost`` per call. Reuses the
existing ``MetricsCollector.COST_PER_1M_TOKENS`` table (no second price table) and
maps local backends (ollama/lmstudio/localai/host) onto the free ``local`` tier.
An unknown provider prices at ``0.0`` — absence yields ``0.0``, never an error.
"""

from __future__ import annotations

from opencontext_core.metrics import MetricsCollector

# Local / host-routed backends bill as the free "local" tier (no external spend).
_LOCAL_ALIASES = frozenset(
    {"ollama", "lmstudio", "localai", "llamacpp", "gpt4all", "host"}
)


def pricing_for(provider: str) -> dict[str, float]:
    """Return ``{"input": $/1M, "output": $/1M}`` pricing for *provider*."""

    table = MetricsCollector.COST_PER_1M_TOKENS
    if provider in table:
        return table[provider]
    if provider in _LOCAL_ALIASES:
        return table["local"]
    return {"input": 0.0, "output": 0.0}


def estimate_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    """Return the estimated USD cost for a call's token counts."""

    price = pricing_for(provider)
    return (input_tokens / 1_000_000) * price.get("input", 0.0) + (
        output_tokens / 1_000_000
    ) * price.get("output", 0.0)
