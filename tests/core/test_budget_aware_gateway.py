"""Tests for BudgetAwareLLMGateway routing."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from opencontext_core.llm.gateway import LLMRequest, LLMResponse
from opencontext_core.runtime import BudgetAwareLLMGateway


class _RecordingGateway:
    """Captures the request actually handed to the base gateway."""

    def __init__(self) -> None:
        self.seen: LLMRequest | None = None

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.seen = request
        return LLMResponse(
            content="ok",
            provider=request.provider,
            model=request.model,
            input_tokens=0,
            output_tokens=1,
        )


class _Router:
    def route_with_budget(self, role: str, complexity: str) -> dict[str, str]:
        return {"provider": "ollama", "model": "local-model"}


class _Budget:
    def consume(self, provider: str, model: str) -> None:
        pass


class _QualityGate:
    def evaluate(self, **_: Any) -> Any:
        return SimpleNamespace(risks=[], reason="ok")


def test_generate_routes_onto_a_copy_without_mutating_caller_request() -> None:
    base = _RecordingGateway()
    gw = BudgetAwareLLMGateway(base, _Router(), _Budget(), _QualityGate())
    request = LLMRequest(
        prompt="hi",
        provider="host",
        model="host-model",
        max_output_tokens=128,
        context_items=[],
        metadata={"role": "generate", "task_complexity": "standard"},
    )

    gw.generate(request)

    # The base gateway saw the routed provider/model...
    assert base.seen is not None
    assert (base.seen.provider, base.seen.model) == ("ollama", "local-model")
    # ...but the caller's original request was NOT mutated (retries stay idempotent).
    assert (request.provider, request.model) == ("host", "host-model")
