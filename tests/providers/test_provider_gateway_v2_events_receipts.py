"""PR-012 Phase 4.6 / CONV.4 — named provider events, receipts, Decision Log.

The facade emits the named ``provider.*`` events, persists
``provider-selection`` / ``provider-call`` / ``fallback`` receipts, and records
each provider choice as a ``RuntimeDecision`` in the Decision Log.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.errors import ProviderError
from opencontext_core.models.llm import LLMRequest, LLMResponse
from opencontext_core.operating_model.events import ProviderEvent, ProviderEventEmitter
from opencontext_core.operating_model.receipts import RunReceiptStore
from opencontext_core.providers.adapters import ModelResponse
from opencontext_core.providers.gateway import ProviderGateway
from opencontext_core.runtime.decision_log import DecisionRecorder
from opencontext_core.runtime.decisions import DecisionKind


class _OkGateway:
    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="ok",
            provider=request.provider,
            model=request.model,
            input_tokens=5,
            output_tokens=3,
        )


class _FailingGateway:
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise ProviderError("boom")


class _StubAdapter:
    def __init__(self, provider: str) -> None:
        self._provider = provider

    def chat_with_retries(self, messages: list[dict[str, str]], **kwargs: object) -> ModelResponse:
        return ModelResponse(
            content="fallback",
            model=str(kwargs.get("model", "m")),
            provider=self._provider,
            input_tokens=1,
            output_tokens=1,
        )


def _req() -> LLMRequest:
    return LLMRequest(prompt="hi", provider="mock", model="mock-llm", max_output_tokens=64)


def _anthropic_req() -> LLMRequest:
    return LLMRequest(prompt="hi", provider="anthropic", model="claude-x", max_output_tokens=64)


def test_success_emits_selected_called_completed_and_receipts(tmp_path: Path) -> None:
    emitter = ProviderEventEmitter()
    receipts = RunReceiptStore(tmp_path)
    gw = ProviderGateway(_OkGateway(), emitter=emitter, receipts=receipts)
    gw.generate(_req())

    kinds = emitter.kinds()
    assert kinds == [ProviderEvent.SELECTED, ProviderEvent.CALLED, ProviderEvent.COMPLETED]

    receipt_kinds = {r.kind for r in receipts.list_provider_receipts()}
    assert "provider-selection" in receipt_kinds
    assert "provider-call" in receipt_kinds


def test_provider_choice_is_recorded_in_the_decision_log() -> None:
    recorder = DecisionRecorder()
    gw = ProviderGateway(_OkGateway(), recorder=recorder)
    gw.generate(_req())

    entries = recorder.entries()
    assert len(entries) >= 1
    decision = entries[0].decision
    assert decision.kind == DecisionKind.provider
    assert "mock" in decision.chosen


def test_fallback_emits_event_and_receipt(tmp_path: Path) -> None:
    emitter = ProviderEventEmitter()
    receipts = RunReceiptStore(tmp_path)
    gw = ProviderGateway(
        _FailingGateway(),
        emitter=emitter,
        receipts=receipts,
        adapter_factory=lambda p: _StubAdapter(p),
        fallback_providers=("mock",),
        retry_limit=2,
    )
    resp = gw.generate(_anthropic_req())
    assert resp.content == "fallback"

    assert ProviderEvent.FAILED in emitter.kinds()
    assert ProviderEvent.FALLBACK in emitter.kinds()

    fallback_receipts = [r for r in receipts.list_provider_receipts() if r.kind == "fallback"]
    assert len(fallback_receipts) == 1
    assert fallback_receipts[0].receipt_id.startswith("pcall_")
