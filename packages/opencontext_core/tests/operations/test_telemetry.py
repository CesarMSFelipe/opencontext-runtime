"""Tests for ``opencontext_core.operations.telemetry``.

Covers REQ-ops-deploy-004 from the spec:
- ``TelemetryOptIn`` matrix per mode
- Default ``opt_in=False`` and a redaction key set
- AIR_GAPPED mode refuses any opt-in override
- Redaction happens at the boundary (the matrix owns the policy, the sender
  uses it)
"""

from __future__ import annotations

import pytest

from opencontext_core.operations.deploy import DeployConfig, DeployMode
from opencontext_core.operations.telemetry import (
    DEFAULT_REDACT_KEYS,
    TelemetryOptIn,
    telemetry_policy_for,
)


class TestDefaultRedactKeys:
    def test_includes_openai_key(self):
        # spec REQ-ops-deploy-004 explicitly lists these keys
        assert "OPENAI_API_KEY" in DEFAULT_REDACT_KEYS

    def test_includes_anthropic_key(self):
        assert "ANTHROPIC_API_KEY" in DEFAULT_REDACT_KEYS

    def test_includes_token_and_secret_glob_patterns(self):
        # spec lists "*_TOKEN" and "*_SECRET" as glob patterns
        assert "*_TOKEN" in DEFAULT_REDACT_KEYS
        assert "*_SECRET" in DEFAULT_REDACT_KEYS


class TestTelemetryOptInMatrix:
    @pytest.mark.parametrize(
        "mode,expected_opt_in",
        [
            (DeployMode.LOCAL, True),
            (DeployMode.CI_RUNNER, False),
            (DeployMode.SHARED_REMOTE, True),
            (DeployMode.HYBRID_EDGE_CLOUD, True),
            (DeployMode.AIR_GAPPED, False),
        ],
    )
    def test_per_mode_default_opt_in(self, mode: DeployMode, expected_opt_in: bool):
        # GIVEN any mode
        policy = telemetry_policy_for(mode)
        # THEN the per-mode default is the expected one
        assert policy.opt_in is expected_opt_in

    def test_air_gapped_refuses_explicit_opt_in(self):
        # GIVEN AIR_GAPPED mode
        # WHEN telemetry_policy_for runs
        # THEN the result NEVER reports opt_in=True even if the caller
        # constructed a DeployConfig that asked for it
        cfg = DeployConfig(mode=DeployMode.AIR_GAPPED, telemetry_opt_in=True)
        policy = telemetry_policy_for(cfg.mode, config=cfg)
        assert policy.opt_in is False

    def test_redact_keys_default_present(self):
        # GIVEN any non-air-gapped mode
        policy = telemetry_policy_for(DeployMode.LOCAL)
        # THEN the redact_keys set is the spec default
        assert policy.redact_keys == DEFAULT_REDACT_KEYS

    def test_sample_rate_in_unit_interval(self):
        # sample_rate is a probability
        for mode in DeployMode:
            p = telemetry_policy_for(mode)
            assert 0.0 <= p.sample_rate <= 1.0

    def test_air_gapped_always_off_even_with_env(self, monkeypatch: pytest.MonkeyPatch):
        # spec: AIR_GAPPED mode SHALL refuse any opt_in=True override
        # (no env var, no flag, no override)
        monkeypatch.setenv("OPENCONTEXT_TELEMETRY", "1")
        policy = telemetry_policy_for(DeployMode.AIR_GAPPED)
        assert policy.opt_in is False

    def test_env_can_flip_non_airgapped_on(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN OPENCONTEXT_TELEMETRY=1 and a non-inviolable mode
        monkeypatch.setenv("OPENCONTEXT_TELEMETRY", "1")
        # WHEN telemetry_policy_for runs
        # THEN opt_in is True
        assert telemetry_policy_for(DeployMode.LOCAL).opt_in is True
        assert telemetry_policy_for(DeployMode.SHARED_REMOTE).opt_in is True


class TestTelemetryOptInDataclass:
    def test_construction(self):
        p = TelemetryOptIn(opt_in=True, sample_rate=0.25, redact_keys={"*_TOKEN"})
        assert p.opt_in is True
        assert p.sample_rate == 0.25
        assert "*_TOKEN" in p.redact_keys

    def test_redact_keys_can_be_extended(self):
        # redactor uses this set; can be passed in extended
        p = TelemetryOptIn(
            opt_in=True, sample_rate=0.1, redact_keys=DEFAULT_REDACT_KEYS | {"CUSTOM"}
        )
        assert "CUSTOM" in p.redact_keys
        assert "OPENAI_API_KEY" in p.redact_keys
