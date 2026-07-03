"""Per-client instruction docs must match the real MCP execution model.

Truth matrix (from the live capability matrix + MCP protocol reality):

* OpenCode advertises the ``sampling`` capability → ``opencontext_run`` executes
  the workflow directly with the client's selected model.
* Claude Code and Codex do NOT sample → with no provider configured,
  ``opencontext_run`` returns the ``agent_execute`` handoff and the agent
  completes the run via ``opencontext_session_apply`` (``kind="agent_edits"``).
* Codex IS an MCP client: the installer registers the server in
  ``~/.codex/config.toml`` (TOML ``mcp_servers``), so its profile must not claim
  MCP tools are unavailable to it.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "packages/opencontext_core/opencontext_core/configurator/profiles"


def _profile(name: str) -> str:
    return (PROFILES / f"{name}.md").read_text(encoding="utf-8")


def test_capability_matrix_pins_sampling_support() -> None:
    from opencontext_core.configurator.capability import build_capability_matrix

    matrix = build_capability_matrix()
    assert matrix.get("opencode").supports_sampling is True
    assert matrix.get("claude-code").supports_sampling is False
    assert matrix.get("codex").supports_sampling is False


def test_claude_code_profile_documents_agent_execute_contract() -> None:
    body = _profile("claude-code")
    assert "agent_execute" in body
    assert "opencontext_session_apply" in body
    assert "agent_edits" in body


def test_codex_profile_documents_mcp_and_agent_execute_contract() -> None:
    body = _profile("codex")
    # Stale claim removed: the installer registers OpenContext as an MCP server
    # for Codex (~/.codex/config.toml), so Codex DOES call the MCP tools.
    assert "MCP tools are not called directly" not in body
    assert "config.toml" in body
    assert "agent_execute" in body
    assert "opencontext_session_apply" in body


def test_opencode_profile_documents_direct_sampling_execution() -> None:
    body = _profile("opencode")
    assert "sampling" in body
    assert "opencontext_run" in body


def test_rendered_instructions_document_both_execution_models() -> None:
    from opencontext_core.agents.template_renderer import render_agent_instructions

    for agent_id in ("claude-code", "codex", "opencode"):
        body = render_agent_instructions(agent_id)
        # Sampling hosts: the run tool executes directly with the host model.
        assert "sampling" in body, agent_id
        # Non-sampling hosts: the agent_execute handoff + exact follow-up.
        assert "agent_execute" in body, agent_id
        assert "opencontext_session_apply" in body, agent_id
        assert "agent_edits" in body, agent_id
