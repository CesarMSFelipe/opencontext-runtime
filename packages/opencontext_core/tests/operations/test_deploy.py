"""Tests for ``opencontext_core.operations.deploy``.

Covers REQ-ops-deploy-001 from the spec:
- 5 named deployment modes
- ``DeployConfig`` shape
- ``detect_deploy_mode()`` reads ``OPENCONTEXT_DEPLOY_MODE`` env var
- AIR_GAPPED forces telemetry_opt_in=False and refuses any override
"""

from __future__ import annotations

import pytest

from opencontext_core.operations.deploy import (
    DeployConfig,
    DeployMode,
    detect_deploy_mode,
)

# ponytail: spec lists 5 modes with these exact names; spec name "AIR_GAPPED"
# gets the SCREAMING_SNAKE spelling to match the other enum members.
EXPECTED_MODE_NAMES = frozenset(
    {"LOCAL", "CI_RUNNER", "SHARED_REMOTE", "HYBRID_EDGE_CLOUD", "AIR_GAPPED"}
)


class TestDeployModeEnum:
    def test_has_exactly_the_five_modes_from_spec(self):
        # GIVEN the spec REQ-ops-deploy-001
        # THEN DeployMode exposes the 5 named modes
        assert {m.name for m in DeployMode} == EXPECTED_MODE_NAMES

    def test_member_count_is_five(self):
        # triangulate: not just names, also cardinality
        assert len(list(DeployMode)) == 5

    def test_air_gapped_is_a_member(self):
        # AIR_GAPPED is the inviolable mode (UVD-014); must exist by name
        assert DeployMode.AIR_GAPPED in DeployMode

    def test_modes_are_distinct(self):
        # no two aliases for the same mode
        assert len({m.value for m in DeployMode}) == 5


class TestDeployConfig:
    def test_minimal_construction_local(self):
        # GIVEN a local deploy config
        cfg = DeployConfig(mode=DeployMode.LOCAL)
        # THEN it carries the mode and a sensible default for remote_url
        assert cfg.mode is DeployMode.LOCAL
        assert cfg.remote_url is None
        assert cfg.telemetry_opt_in is False

    def test_remote_url_for_shared_remote(self):
        # GIVEN SHARED_REMOTE mode and a remote URL
        cfg = DeployConfig(
            mode=DeployMode.SHARED_REMOTE,
            remote_url="http://127.0.0.1:7443",
        )
        # THEN the URL is preserved
        assert cfg.remote_url == "http://127.0.0.1:7443"
        assert cfg.mode is DeployMode.SHARED_REMOTE

    def test_air_gapped_forces_telemetry_off(self):
        # GIVEN AIR_GAPPED mode and a deliberate opt-in attempt
        cfg = DeployConfig(
            mode=DeployMode.AIR_GAPPED,
            telemetry_opt_in=True,  # attempt to override
        )
        # THEN AIR_GAPPED wins — opt_in is forced off
        assert cfg.telemetry_opt_in is False

    def test_hybrid_keeps_user_opt_in(self):
        # triangulate: AIR_GAPPED is the only inviolable mode
        cfg = DeployConfig(mode=DeployMode.HYBRID_EDGE_CLOUD, telemetry_opt_in=True)
        assert cfg.telemetry_opt_in is True

    def test_config_is_immutable(self):
        # DeployConfig is a frozen dataclass — post-construction mutation is forbidden
        cfg = DeployConfig(mode=DeployMode.LOCAL)
        with pytest.raises((AttributeError, Exception)):
            cfg.mode = DeployMode.CI_RUNNER  # type: ignore[misc]


class TestDetectDeployMode:
    def test_default_is_local_when_env_unset(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN no env var
        monkeypatch.delenv("OPENCONTEXT_DEPLOY_MODE", raising=False)
        # WHEN detect_deploy_mode runs
        # THEN it returns LOCAL (developer default per spec doc 33)
        assert detect_deploy_mode() is DeployMode.LOCAL

    def test_reads_opencontext_deploy_mode_env(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN OPENCONTEXT_DEPLOY_MODE=ci_runner
        monkeypatch.setenv("OPENCONTEXT_DEPLOY_MODE", "ci_runner")
        # WHEN detect_deploy_mode runs
        # THEN it returns CI_RUNNER
        assert detect_deploy_mode() is DeployMode.CI_RUNNER

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("local", DeployMode.LOCAL),
            ("ci", DeployMode.CI_RUNNER),
            ("ci_runner", DeployMode.CI_RUNNER),
            ("remote", DeployMode.SHARED_REMOTE),
            ("shared_remote", DeployMode.SHARED_REMOTE),
            ("hybrid", DeployMode.HYBRID_EDGE_CLOUD),
            ("air-gapped", DeployMode.AIR_GAPPED),
            ("air_gapped", DeployMode.AIR_GAPPED),
        ],
    )
    def test_accepts_canonical_and_alias_names(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: DeployMode
    ):
        # GIVEN any spelling the CLI / docs may produce
        monkeypatch.setenv("OPENCONTEXT_DEPLOY_MODE", raw)
        # WHEN detect_deploy_mode runs
        # THEN it normalises to the canonical enum value
        assert detect_deploy_mode() is expected

    def test_unknown_value_raises(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN a typo / unknown value
        monkeypatch.setenv("OPENCONTEXT_DEPLOY_MODE", "spaceship")
        # WHEN detect_deploy_mode runs
        # THEN a ValueError surfaces the bad value
        with pytest.raises(ValueError, match="spaceship"):
            detect_deploy_mode()

    def test_empty_string_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch):
        # GIVEN an empty string (some shells export it that way)
        monkeypatch.setenv("OPENCONTEXT_DEPLOY_MODE", "")
        # WHEN detect_deploy_mode runs
        # THEN it falls back to LOCAL
        assert detect_deploy_mode() is DeployMode.LOCAL
