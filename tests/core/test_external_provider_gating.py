"""external-provider gating for `review --party`.

External LLM sends MUST route through ContextFirewall + provider policy +
redaction, and MUST be blocked in secure/air-gapped mode.
"""

from __future__ import annotations

import pytest

from opencontext_cli.commands.review_cmd import (
    ProviderBlockedError,
    guard_external_send,
)
from opencontext_core.config import (
    OpenContextConfig,
    ProviderPolicyConfig,
    SecurityMode,
    default_config_data,
)


def _config(
    *,
    mode: SecurityMode = SecurityMode.PRIVATE_PROJECT,
    external_enabled: bool = True,
    provider: str = "anthropic",
    allowed: bool = True,
) -> OpenContextConfig:
    data = default_config_data()
    data["security"]["mode"] = mode.value
    data["security"]["external_providers_enabled"] = external_enabled
    cfg = OpenContextConfig.model_validate(data)
    cfg = cfg.model_copy(
        update={
            "provider_policies": [
                ProviderPolicyConfig(
                    provider=provider,
                    allowed=allowed,
                    allowed_classifications={"public", "internal"},
                    require_redaction=True,
                )
            ]
        }
    )
    return cfg


def test_air_gapped_blocks_external_send() -> None:
    """Air-gapped mode blocks any non-local provider send."""
    cfg = _config(mode=SecurityMode.AIR_GAPPED)
    with pytest.raises(ProviderBlockedError) as exc:
        guard_external_send("anthropic", "def f(): pass", config=cfg)
    assert "air_gapped" in str(exc.value).lower() or "blocked" in str(exc.value).lower()


def test_external_disabled_blocks_send() -> None:
    """external_providers_enabled=False blocks non-local providers."""
    cfg = _config(external_enabled=False)
    with pytest.raises(ProviderBlockedError):
        guard_external_send("anthropic", "secret code", config=cfg)


def test_secret_in_context_is_blocked_by_firewall() -> None:
    """A raw secret in the review context is blocked before the external send."""
    cfg = _config()
    leaky = 'aws_key = "AKIAIOSFODNN7EXAMPLE"\nsecret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"'
    with pytest.raises(ProviderBlockedError):
        guard_external_send("anthropic", leaky, config=cfg)


def test_allowed_provider_passes_and_returns_redacted_payload() -> None:
    """An allowed provider in a permissive mode passes and returns a payload."""
    cfg = _config()
    payload = guard_external_send("anthropic", "def add(a, b):\n    return a + b", config=cfg)
    assert isinstance(payload, str)
    assert "add" in payload


def test_disallowed_provider_policy_blocks() -> None:
    """A provider without an allowing policy is blocked."""
    cfg = _config(provider="anthropic", allowed=False)
    with pytest.raises(ProviderBlockedError):
        guard_external_send("anthropic", "code", config=cfg)


def test_local_provider_is_not_gated() -> None:
    """Local providers (mock/local) are never gated as external."""
    cfg = _config(mode=SecurityMode.AIR_GAPPED)
    # mock is local — must not raise even in air-gapped mode.
    payload = guard_external_send("mock", "def f(): return 1", config=cfg)
    assert "f" in payload
