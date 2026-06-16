from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import opencontext_cli.commands.setup_cmd as setup_cmd
from opencontext_core.adapters.agent_manifest import AgentIntegrationGenerator, AgentTarget
from opencontext_core.sdd_profiles import (
    CLIENT_ORCHESTRATOR_PROFILES,
    ORCHESTRATOR_TYPES,
    get_client_orchestrator_profile,
)
from opencontext_core.sdd_runtime import build_sdd_context, write_sdd_context
from opencontext_core.setup.plan import build_plan
from opencontext_core.user_prefs import UserConfigStore


class FakeRuntime:
    def index_project(self, root: str | Path) -> SimpleNamespace:
        return SimpleNamespace(files=["a.py"], symbols=["main"])


class FakeAgentInstaller:
    calls: ClassVar[list[dict[str, object]]] = []

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root)

    def install(self, *, targets: list[object], location: str, yes: bool) -> dict[str, object]:
        self.calls.append({"targets": [str(t) for t in targets], "location": location, "yes": yes})
        return {"status": "installed"}


class TestClientOrchestratorProfile:
    def test_all_orchestrator_types_are_valid(self) -> None:
        for profile in CLIENT_ORCHESTRATOR_PROFILES.values():
            assert profile.orchestrator_type in ORCHESTRATOR_TYPES

    def test_opencode_is_multi_phase(self) -> None:
        profile = get_client_orchestrator_profile("opencode")
        assert profile.orchestrator_type == "opencontext"
        assert profile.kg_lookup_first is True

    def test_kilo_code_is_multi_phase(self) -> None:
        profile = get_client_orchestrator_profile("kilo-code")
        assert profile.orchestrator_type == "opencontext"

    def test_cursor_is_subagent_native(self) -> None:
        profile = get_client_orchestrator_profile("cursor")
        assert profile.orchestrator_type == "subagent-native"
        assert "background" in profile.delegation_hint.lower()

    def test_kiro_is_subagent_native(self) -> None:
        profile = get_client_orchestrator_profile("kiro-ide")
        assert profile.orchestrator_type == "subagent-native"
        assert ".kiro/specs" in profile.delegation_hint

    def test_codex_is_solo_compact(self) -> None:
        profile = get_client_orchestrator_profile("codex")
        assert profile.orchestrator_type == "opencontext"

    def test_windsurf_is_solo_compact(self) -> None:
        profile = get_client_orchestrator_profile("windsurf")
        assert profile.orchestrator_type == "solo-compact"

    def test_claude_code_is_solo_compact(self) -> None:
        profile = get_client_orchestrator_profile("claude-code")
        assert profile.orchestrator_type == "solo-compact"

    def test_unknown_client_falls_back_to_solo_compact(self) -> None:
        profile = get_client_orchestrator_profile("my-custom-agent")
        assert profile.orchestrator_type == "solo-compact"
        assert profile.kg_lookup_first is True

    def test_all_known_profiles_have_all_sdd_phases(self) -> None:
        phases = {"explore", "propose", "spec", "design", "tasks", "apply", "verify", "archive"}
        for client, profile in CLIENT_ORCHESTRATOR_PROFILES.items():
            assert set(profile.phase_instructions.keys()) == phases, (
                f"{client} missing phase instructions"
            )

    def test_phase_instruction_returns_empty_for_unknown_phase(self) -> None:
        profile = get_client_orchestrator_profile("opencode")
        assert profile.phase_instruction("nonexistent") == ""

    def test_to_dict_round_trips(self) -> None:
        profile = get_client_orchestrator_profile("cursor")
        data = profile.to_dict()
        assert data["client"] == "cursor"
        assert data["orchestrator_type"] == "subagent-native"
        assert isinstance(data["phase_instructions"], dict)

    def test_multi_phase_explore_mentions_kg(self) -> None:
        profile = get_client_orchestrator_profile("opencode")
        assert "opencontext pack" in profile.phase_instruction("explore").lower()

    def test_subagent_native_explore_mentions_spawn(self) -> None:
        profile = get_client_orchestrator_profile("cursor")
        assert "spawn" in profile.phase_instruction("explore").lower()

    def test_solo_compact_explore_mentions_pack_once(self) -> None:
        profile = get_client_orchestrator_profile("codex")
        assert "smallest useful evidence" in profile.phase_instruction("explore").lower()

    def test_all_profiles_have_tdd_integration(self) -> None:
        for client, profile in CLIENT_ORCHESTRATOR_PROFILES.items():
            assert profile.tdd_integration, f"{client} missing tdd_integration"


class TestOrchestratorSectionInGeneratedFiles:
    def test_opencode_agents_md_contains_orchestrator_section(self, tmp_path: Path) -> None:
        AgentIntegrationGenerator().generate(tmp_path, target=AgentTarget.OPENCODE)
        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "Orchestrator profile: opencontext" in content
        assert "OpenContext" in content
        assert "Per-phase instructions" in content

    def test_cursor_rule_contains_subagent_native_section(self, tmp_path: Path) -> None:
        AgentIntegrationGenerator().generate(tmp_path, target=AgentTarget.CURSOR)
        content = (tmp_path / ".cursor" / "rules" / "opencontext.mdc").read_text(encoding="utf-8")
        assert "Orchestrator profile: subagent-native" in content
        assert "background" in content.lower()

    def test_codex_agents_md_contains_solo_compact_section(self, tmp_path: Path) -> None:
        AgentIntegrationGenerator().generate(tmp_path, target=AgentTarget.CODEX)
        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "Orchestrator profile: opencontext" in content

    def test_windsurf_rule_contains_solo_compact_section(self, tmp_path: Path) -> None:
        AgentIntegrationGenerator().generate(tmp_path, target=AgentTarget.WINDSURF)
        content = (tmp_path / ".windsurf" / "rules" / "opencontext.md").read_text(encoding="utf-8")
        assert "Orchestrator profile: solo-compact" in content

    def test_kiro_steering_contains_subagent_native_section(self, tmp_path: Path) -> None:
        AgentIntegrationGenerator().generate(tmp_path, target=AgentTarget.KIRO_IDE)
        content = (tmp_path / ".kiro" / "steering" / "opencontext.md").read_text(encoding="utf-8")
        assert "Orchestrator profile: subagent-native" in content
        assert ".kiro/specs" in content

    def test_opencode_json_references_sdd_context(self, tmp_path: Path) -> None:
        AgentIntegrationGenerator().generate(tmp_path, target=AgentTarget.OPENCODE)
        data = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
        assert ".opencontext/sdd/context.json" in data["instructions"]

    def test_claude_md_contains_orchestrator_section(self, tmp_path: Path) -> None:
        AgentIntegrationGenerator().generate(tmp_path, target=AgentTarget.CLAUDE_CODE)
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "Orchestrator profile: solo-compact" in content


class TestSDDContextOrchestrationFields:
    def test_build_sdd_context_includes_active_clients(self, tmp_path: Path) -> None:
        context = build_sdd_context(
            tmp_path,
            active_clients=["opencode", "cursor"],
        )
        assert context.active_clients == ["opencode", "cursor"]

    def test_build_sdd_context_maps_orchestrator_types(self, tmp_path: Path) -> None:
        context = build_sdd_context(
            tmp_path,
            active_clients=["opencode", "cursor", "codex"],
        )
        assert context.orchestrator_profiles["opencode"] == "opencontext"
        assert context.orchestrator_profiles["cursor"] == "subagent-native"
        assert context.orchestrator_profiles["codex"] == "opencontext"

    def test_build_sdd_context_stores_sdd_model_profile(self, tmp_path: Path) -> None:
        context = build_sdd_context(tmp_path, sdd_model_profile="cheap")
        assert context.sdd_model_profile == "cheap"

    def test_build_sdd_context_stores_execution_and_artifact_modes(self, tmp_path: Path) -> None:
        context = build_sdd_context(
            tmp_path,
            execution_mode="manual",
            artifact_mode="engram",
        )

        assert context.execution_mode == "manual"
        assert context.artifact_mode == "engram"

    def test_build_sdd_context_defaults_to_default_profile(self, tmp_path: Path) -> None:
        context = build_sdd_context(tmp_path)
        assert context.sdd_model_profile == "default"
        assert context.active_clients == []
        assert context.orchestrator_profiles == {}

    def test_write_sdd_context_persists_orchestrator_profiles(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        write_sdd_context(
            tmp_path,
            active_clients=["opencode", "cursor"],
            sdd_model_profile="hybrid",
        )
        data = json.loads((tmp_path / ".opencontext" / "sdd" / "context.json").read_text())
        assert data["orchestrator_profiles"]["opencode"] == "opencontext"
        assert data["orchestrator_profiles"]["cursor"] == "subagent-native"
        assert data["sdd_model_profile"] == "hybrid"
        assert data["active_clients"] == ["opencode", "cursor"]

    def test_testing_md_includes_orchestrator_profiles_section(self, tmp_path: Path) -> None:
        write_sdd_context(
            tmp_path,
            active_clients=["opencode", "cursor"],
            sdd_model_profile="cheap",
        )
        md = (tmp_path / ".opencontext" / "sdd" / "testing.md").read_text(encoding="utf-8")
        assert "Client orchestrator profiles" in md
        assert "opencontext" in md
        assert "subagent-native" in md
        assert "SDD model profile: `cheap`" in md
        assert "Artifact mode: `hybrid`" in md

    def test_instructions_include_kg_first_rule(self, tmp_path: Path) -> None:
        context = build_sdd_context(tmp_path)
        kg_instructions = [i for i in context.instructions if "knowledge graph" in i.lower()]
        assert kg_instructions, "KG-first rule missing from instructions"

    def test_instructions_include_context_json_rule(self, tmp_path: Path) -> None:
        context = build_sdd_context(tmp_path)
        assert any("context.json" in i for i in context.instructions)


class TestSetupExperienceWithSddProfile:
    def test_execute_plan_stores_sdd_model_profile(self, tmp_path: Path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", config_dir / "user-config.json")
        monkeypatch.setattr(setup_cmd, "OpenContextRuntime", FakeRuntime)
        monkeypatch.setattr(setup_cmd, "AgentInstaller", FakeAgentInstaller)
        FakeAgentInstaller.calls.clear()

        project = tmp_path / "project"
        project.mkdir()
        plan = build_plan(preset_id="context-essential", profile_id="developer")

        setup_cmd._execute_plan(
            plan,
            agents=["opencode", "cursor"],
            tdd_mode="ask",
            root=str(project),
            max_tokens=2400,
            sdd_profile="cheap",
        )

        prefs = json.loads((config_dir / "user-config.json").read_text(encoding="utf-8"))
        assert prefs["sdd_model_profile"] == "cheap"

        ctx = json.loads(
            (project / ".opencontext" / "sdd" / "context.json").read_text(encoding="utf-8")
        )
        assert ctx["sdd_model_profile"] == "cheap"
        assert ctx["orchestrator_profiles"]["opencode"] == "opencontext"
        assert ctx["orchestrator_profiles"]["cursor"] == "subagent-native"
        assert ctx["active_clients"] == ["opencode", "cursor"]

    def test_execute_plan_with_hybrid_profile(self, tmp_path: Path, monkeypatch) -> None:
        config_dir = tmp_path / "config"
        monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", config_dir / "user-config.json")
        monkeypatch.setattr(setup_cmd, "OpenContextRuntime", FakeRuntime)
        monkeypatch.setattr(setup_cmd, "AgentInstaller", FakeAgentInstaller)
        FakeAgentInstaller.calls.clear()

        project = tmp_path / "project"
        project.mkdir()
        plan = build_plan(preset_id="context-essential", profile_id="developer")

        setup_cmd._execute_plan(
            plan,
            agents=["opencode"],
            tdd_mode="strict",
            root=str(project),
            max_tokens=3000,
            sdd_profile="hybrid",
        )

        ctx = json.loads(
            (project / ".opencontext" / "sdd" / "context.json").read_text(encoding="utf-8")
        )
        assert ctx["sdd_model_profile"] == "hybrid"
        assert ctx["tdd_mode"] == "strict"

    def test_choose_sdd_profile_returns_valid_option(self, monkeypatch) -> None:
        monkeypatch.setattr("opencontext_cli.commands.setup_cmd.Prompt.ask", lambda *a, **kw: "2")
        result = setup_cmd._choose_sdd_profile()
        assert result == "cheap"

    def test_choose_sdd_profile_default_is_default(self, monkeypatch) -> None:
        monkeypatch.setattr("opencontext_cli.commands.setup_cmd.Prompt.ask", lambda *a, **kw: "1")
        result = setup_cmd._choose_sdd_profile()
        assert result == "default"
