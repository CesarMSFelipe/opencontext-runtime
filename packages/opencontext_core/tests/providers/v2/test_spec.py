"""REQ-pg-v2-001: 7 capability flags on CapabilityModel."""

from __future__ import annotations

from opencontext_core.providers.v2.spec import (
    CAPABILITY_FLAGS,
    CapabilityModel,
    ProviderSpec,
)


def test_REQ_pg_v2_001_seven_capabilities() -> None:
    assert CAPABILITY_FLAGS == (
        "structured_output",
        "tool_use",
        "long_context",
        "reasoning",
        "streaming",
        "vision",
        "embeddings",
    )


def test_capability_model_seven_booleans() -> None:
    caps = CapabilityModel(
        structured_output=True,
        tool_use=True,
        long_context=False,
        reasoning=True,
        streaming=True,
        vision=False,
        embeddings=False,
    )
    assert caps.structured_output is True
    assert caps.tool_use is True
    assert caps.long_context is False
    assert caps.embeddings is False


def test_provider_spec_carries_capabilities() -> None:
    spec = ProviderSpec(
        provider_id="mock-llm",
        display_name="Mock LLM",
        capabilities=CapabilityModel(),
        cost_input_per_1k=0.0,
        cost_output_per_1k=0.0,
        max_context_tokens=8192,
        avg_latency_ms=10,
        quality_score=0.5,
    )
    assert spec.provider_id == "mock-llm"
    assert spec.capabilities.structured_output is False