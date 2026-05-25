"""Tests for AgentCapabilities registry."""

from __future__ import annotations

from opencontext_core.agents.registry import (
    AGENT_CAPABILITIES,
    get_agent_capabilities,
    list_supported_agents,
)


class TestAgentCapabilities:
    def test_opencode_has_correct_capabilities(self) -> None:
        cap = get_agent_capabilities("opencode")
        assert cap is not None
        assert cap.can_edit_files is True
        assert cap.can_run_shell is True
        assert cap.supports_mcp is True
        assert cap.orchestrator_type == "multi-phase"

    def test_cursor_supports_subagents(self) -> None:
        cap = get_agent_capabilities("cursor")
        assert cap is not None
        assert cap.supports_subagents is True
        assert cap.orchestrator_type == "subagent-native"

    def test_aider_is_proposal_only(self) -> None:
        cap = get_agent_capabilities("aider")
        assert cap is not None
        assert cap.supports_proposal_only is True
        assert cap.can_run_shell is False

    def test_unknown_agent_returns_none(self) -> None:
        cap = get_agent_capabilities("nonexistent-agent")
        assert cap is None

    def test_all_agents_have_required_fields(self) -> None:
        for client_id, cap in AGENT_CAPABILITIES.items():
            assert cap.id == client_id, f"{client_id} id mismatch"
            assert cap.display_name, f"{client_id} missing display_name"
            assert cap.orchestrator_type in ("solo-compact", "multi-phase", "subagent-native"), (
                f"{client_id} bad orchestrator_type"
            )

    def test_list_includes_new_agents(self) -> None:
        agents = list_supported_agents()
        ids = {a["id"] for a in agents}
        assert "opencode" in ids
        assert "cursor" in ids
        assert "aider" in ids
        assert "cline" in ids
        assert "roo" in ids
        assert "goose" in ids
        assert "continue" in ids
        assert "openhands" in ids

    def test_list_returns_expected_keys(self) -> None:
        agents = list_supported_agents()
        for entry in agents:
            assert "id" in entry
            assert "display_name" in entry
            assert "orchestrator_type" in entry
            assert "can_edit_files" in entry

    def test_claude_code_no_subagents(self) -> None:
        cap = get_agent_capabilities("claude-code")
        assert cap is not None
        assert cap.supports_subagents is False

    def test_copilot_cli_cannot_edit_files(self) -> None:
        cap = get_agent_capabilities("copilot-cli")
        assert cap is not None
        assert cap.can_edit_files is False
        assert cap.can_run_shell is False
