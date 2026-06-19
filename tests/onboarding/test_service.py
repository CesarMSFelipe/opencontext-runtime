"""Tests for OnboardingService."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from opencontext_core.onboarding.service import (
    OnboardingOptions,
    OnboardingResult,
    OnboardingService,
)


def test_onboarding_options_defaults() -> None:
    opts = OnboardingOptions(root=Path("/tmp/test"))
    assert opts.tdd_mode == "ask"
    assert opts.sdd_model_profile == "hybrid"
    assert opts.orchestrator_profile == "multi-phase"
    assert opts.active_clients == ["opencode"]
    assert opts.token_budget_per_phase is None
    assert opts.force_agent_files is False
    assert opts.setup_mcp is False


def test_onboarding_options_custom() -> None:
    opts = OnboardingOptions(
        root=Path("/tmp/test"),
        tdd_mode="strict",
        sdd_model_profile="premium",
        orchestrator_profile="solo-compact",
        active_clients=["opencode", "cursor"],
        force_agent_files=True,
        setup_mcp=True,
        token_budget_per_phase=6000,
    )
    assert opts.tdd_mode == "strict"
    assert opts.sdd_model_profile == "premium"
    assert opts.orchestrator_profile == "solo-compact"
    assert opts.active_clients == ["opencode", "cursor"]
    assert opts.token_budget_per_phase == 6000


def test_onboarding_result_defaults() -> None:
    r = OnboardingResult(root="/tmp/test", config_path="/tmp/test/opencontext.yaml")
    assert r.indexed_files == 0
    assert r.knowledge_graph_nodes == 0
    assert r.warnings == []
    assert r.mcp_configured is False


def test_onboarding_service_run_creates_workspace(tmp_path: Path) -> None:
    """Verify OnboardingService.run() creates .opencontext directory."""
    service = OnboardingService()
    result = service.run(OnboardingOptions(root=tmp_path, force_agent_files=True))
    assert (tmp_path / ".opencontext").exists()
    assert result.root == str(tmp_path.resolve())


def test_onboarding_writes_gitignore_storage_block(tmp_path: Path) -> None:
    """M9: install/onboard (not just setup) must keep the local index out of git."""
    OnboardingService().run(OnboardingOptions(root=tmp_path))
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".storage/" in gitignore
    assert ".opencontext/" in gitignore


def test_onboarding_bridges_runtime_prefs_into_yaml(tmp_path: Path) -> None:
    """M6: prefs the runtime reads from yaml (e.g. security mode) must be synced
    during onboarding, not just saved to the prefs store."""
    service = OnboardingService()
    service.run(OnboardingOptions(root=tmp_path, security_mode="air_gapped"))

    config = yaml.safe_load((tmp_path / "opencontext.yaml").read_text(encoding="utf-8"))
    assert config["security"]["mode"] == "air_gapped"


def test_onboarding_service_creates_config(tmp_path: Path) -> None:
    service = OnboardingService()
    result = service.run(OnboardingOptions(root=tmp_path))
    config = tmp_path / "opencontext.yaml"
    assert config.exists()
    assert result.config_path == str(config)

    import yaml

    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert "security" in data
    assert "project_index" in data


def test_onboarding_service_creates_sdd_context(tmp_path: Path) -> None:
    service = OnboardingService()
    _result = service.run(OnboardingOptions(root=tmp_path, force_agent_files=True))
    sdd_json = tmp_path / ".opencontext" / "sdd" / "context.json"
    assert sdd_json.exists()
    data = json.loads(sdd_json.read_text(encoding="utf-8"))
    assert data["tdd_mode"] == "ask"
    assert "opencode" in data["active_clients"]


def test_onboarding_service_creates_harness_yaml(tmp_path: Path) -> None:
    service = OnboardingService()
    result = service.run(OnboardingOptions(root=tmp_path, force_agent_files=True))
    harness = tmp_path / ".opencontext" / "harness.yaml"
    assert harness.exists()
    assert result.harness_config_path == str(harness)
    data = yaml.safe_load(harness.read_text(encoding="utf-8"))
    assert data["version"] == "0.1"
    assert "explore" in data["phases"]
    assert "apply" in data["phases"]
    assert "safety" in data
    assert "forbidden_paths" in data["safety"]


def test_onboarding_service_creates_agent_contracts(tmp_path: Path) -> None:
    service = OnboardingService()
    _result = service.run(
        OnboardingOptions(
            root=tmp_path,
            active_clients=["opencode", "cursor"],
            force_agent_files=True,
        )
    )
    agent_dir = tmp_path / ".opencontext" / "agents"
    assert (agent_dir / "opencode.md").exists()
    assert (agent_dir / "cursor.md").exists()
    content = (agent_dir / "opencode.md").read_text(encoding="utf-8")
    assert "OpenContext Agent Contract: opencode" in content
    assert "multi-phase" in content
    assert "TDD mode: `ask`" in content


def test_onboarding_service_sdd_context_content(tmp_path: Path) -> None:
    service = OnboardingService()
    service.run(
        OnboardingOptions(
            root=tmp_path,
            tdd_mode="strict",
            sdd_model_profile="premium",
            active_clients=["opencode", "cursor"],
            force_agent_files=True,
        )
    )
    data = json.loads(
        (tmp_path / ".opencontext" / "sdd" / "context.json").read_text(encoding="utf-8")
    )
    assert data["tdd_mode"] == "strict"
    assert data["sdd_model_profile"] == "premium"
    assert data["active_clients"] == ["opencode", "cursor"]
    assert "opencode" in data["orchestrator_profiles"]


def test_onboarding_service_saves_preferences(tmp_path: Path, monkeypatch: Any) -> None:
    from opencontext_core.user_prefs import UserConfigStore

    config_dir = tmp_path / "config"
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", config_dir / "user-config.json")

    service = OnboardingService()
    service.run(
        OnboardingOptions(
            root=tmp_path,
            tdd_mode="strict",
            sdd_model_profile="premium",
            orchestrator_profile="solo-compact",
            active_clients=["opencode", "cursor"],
            force_agent_files=True,
        )
    )

    prefs = json.loads((config_dir / "user-config.json").read_text(encoding="utf-8"))
    assert prefs["sdd"]["tdd_mode"] == "strict"
    assert prefs["sdd"]["sdd_model_profile"] == "premium"
    assert prefs["sdd"]["orchestrator_profile"] == "solo-compact"
    assert prefs["agents"]["active_clients"] == ["opencode", "cursor"]


def test_onboarding_merges_existing_instructions_and_uninstall_reverses(tmp_path: Path) -> None:
    """Install MERGES a managed block into an existing AGENTS.md (no silent skip),
    and `uninstall` removes exactly that block, leaving the user's content."""
    from opencontext_core.configurator.service import Configurator

    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# My project rules\nDo the thing.\n", encoding="utf-8")

    # No force_agent_files: the old generator skipped existing files; Configurator merges.
    OnboardingService().run(OnboardingOptions(root=tmp_path, active_clients=["opencode"]))

    merged = agents_md.read_text(encoding="utf-8")
    assert "# My project rules" in merged  # user content preserved
    assert "<!-- opencontext:instructions:start -->" in merged  # OC block added, not skipped

    Configurator(tmp_path).deconfigure_one("opencode")
    after = agents_md.read_text(encoding="utf-8")
    assert "# My project rules" in after  # user content survives uninstall
    assert "opencontext:instructions" not in after  # OC block fully reversed


def test_onboarding_service_harness_yaml_enterprise(tmp_path: Path) -> None:
    service = OnboardingService()
    service.run(
        OnboardingOptions(
            root=tmp_path,
            template="enterprise",
            force_agent_files=True,
        )
    )
    data = yaml.safe_load((tmp_path / ".opencontext" / "harness.yaml").read_text(encoding="utf-8"))
    assert data["agents"]["default_client"] == "opencode"
    assert data["agents"]["mode"] == "multi-phase"
