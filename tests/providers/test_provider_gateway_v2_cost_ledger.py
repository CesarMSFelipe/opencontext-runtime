"""PR-012 Phase 4.5 / CONV — provider-call cost/latency ledger + RI feed.

A completed call records a ``CostEntry`` (tokens, latency, model, routing reason)
priced from the provider cost model and forwards it best-effort into the
Runtime-Intelligence feed. A ledger failure must NEVER change the response.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.models.llm import LLMRequest, LLMResponse
from opencontext_core.operating_model.performance import CostLedger
from opencontext_core.providers.cost_model import estimate_cost
from opencontext_core.providers.gateway import ProviderGateway


class _Gateway:
    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="ok",
            provider=request.provider,
            model=request.model,
            input_tokens=120,
            output_tokens=40,
        )


class _ExplodingLedger:
    def record(self, entry: Any) -> None:
        raise RuntimeError("ledger down")


def _req() -> LLMRequest:
    return LLMRequest(
        prompt="hi",
        provider="anthropic",
        model="claude-x",
        max_output_tokens=64,
        metadata={"query": "explain auth"},
    )


def test_completed_call_records_a_cost_entry() -> None:
    ledger = CostLedger()
    gw = ProviderGateway(_Gateway(), ledger=ledger)
    gw.generate(_req())

    assert len(ledger.entries) == 1
    entry = ledger.entries[0]
    assert entry.provider == "anthropic"
    assert entry.model == "claude-x"
    assert entry.input_tokens == 120
    assert entry.output_tokens == 40
    assert entry.routing_reason  # a non-empty reason was recorded
    assert entry.actual_latency is not None and entry.actual_latency >= 0.0
    # Priced from the provider cost model.
    assert entry.estimated_cost == estimate_cost("anthropic", 120, 40)
    assert entry.estimated_cost > 0.0


def test_metrics_are_forwarded_to_the_runtime_intelligence_feed() -> None:
    seen: list[dict[str, Any]] = []

    def _feed(orchestrator: Any, **kwargs: Any) -> None:
        seen.append(kwargs)

    gw = ProviderGateway(_Gateway(), ledger=CostLedger(), feed=_feed, learning=object())
    gw.generate(_req())

    assert len(seen) == 1
    assert seen[0]["operation_type"] == "provider_call"
    assert seen[0]["tokens_used"] == 160


def test_ledger_failure_does_not_change_the_response() -> None:
    gw = ProviderGateway(_Gateway(), ledger=_ExplodingLedger())
    resp = gw.generate(_req())
    assert resp.content == "ok"  # best-effort recording never breaks generation
