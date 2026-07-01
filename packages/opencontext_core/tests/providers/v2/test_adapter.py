"""ProviderAdapter Protocol — minimal, structural typing."""

from __future__ import annotations

from dataclasses import dataclass

from opencontext_core.providers.v2.adapter import ProviderAdapter
from opencontext_core.providers.v2.spec import ProviderSpec


@dataclass
class _FakeAdapter:
    provider_id: str = "fake"

    def spec(self) -> ProviderSpec:
        return ProviderSpec(
            provider_id=self.provider_id,
            display_name="Fake",
            cost_input_per_1k=0.0,
            cost_output_per_1k=0.0,
            max_context_tokens=4096,
            avg_latency_ms=1,
            quality_score=0.5,
        )

    def call(self, prompt: str, **kwargs) -> str:
        return f"echo: {prompt}"


def test_provider_adapter_protocol_accepts_structural_impl() -> None:
    # Structural typing: any object with spec() + call() satisfies ProviderAdapter.
    adapter: ProviderAdapter = _FakeAdapter()
    assert adapter.spec().provider_id == "fake"
    assert adapter.call("hi") == "echo: hi"