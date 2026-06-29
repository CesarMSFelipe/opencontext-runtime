"""PROD-004 / B1: doctor states OC Flow mutation needs a provider/MCP sampler/test_stub."""

from __future__ import annotations

import opencontext_core.providers.detect as detect_mod
from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.doctor.checks import _check_provider
from opencontext_core.providers.detect import DetectedProvider


def _config() -> OpenContextConfig:
    return OpenContextConfig.model_validate(default_config_data())


def test_provider_check_states_mutation_requirement_when_none(monkeypatch) -> None:
    # No provider / MCP sampler configured (source == "fallback").
    monkeypatch.setattr(
        detect_mod,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )

    check = _check_provider(_config())
    detail = check.details.lower()

    # ok=True: no provider is fine for non-mutation features.
    assert check.ok is True
    # The message must name the mutation requirement and at least the remedies.
    assert "mutation" in detail
    assert "provider" in detail
    assert "mcp sampler" in detail
    assert "test_stub" in detail
    # Read-only features must still be called out as unaffected.
    assert "without one" in detail or "unaffected" in detail


def test_provider_check_reports_configured_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        detect_mod,
        "detect_provider",
        lambda: DetectedProvider(
            name="anthropic", api_key="x", model="claude-sonnet-4-6", source="ANTHROPIC_API_KEY"
        ),
    )

    check = _check_provider(_config())

    assert check.ok is True
    assert "anthropic" in check.details.lower()
    # The no-provider mutation nudge is not shown when a provider is present.
    assert "needs_executor" not in check.details
