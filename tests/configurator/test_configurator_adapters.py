"""Per-agent adapters declare the right files, shapes, and AGENTS.md behavior."""

from __future__ import annotations

from opencontext_core.configurator.adapter import get_adapter, iter_adapters
from opencontext_core.configurator.mcp_strategy import McpShape


def test_claude_code_uses_claude_md_and_mcp_servers() -> None:
    a = get_adapter("claude-code")
    assert a.instructions_filename == "CLAUDE.md"
    assert a.honors_agents_md is False
    assert a.mcp_shape is McpShape.JSON_MCP_SERVERS


def test_gemini_uses_gemini_md() -> None:
    a = get_adapter("gemini-cli")
    assert a.instructions_filename == "GEMINI.md"


def test_qwen_uses_qwen_md() -> None:
    a = get_adapter("qwen-code")
    assert a.instructions_filename == "QWEN.md"


def test_agents_md_honoring_agents_use_agents_md() -> None:
    for agent_id in ("codex", "opencode", "cursor", "windsurf", "kiro-ide"):
        a = get_adapter(agent_id)
        assert a.honors_agents_md is True, agent_id
        assert a.instructions_filename == "AGENTS.md", agent_id


def test_vscode_copilot_uses_servers_root_key() -> None:
    a = get_adapter("vscode-copilot")
    assert a.mcp_shape is McpShape.JSON_SERVERS


def test_codex_uses_toml_shape() -> None:
    a = get_adapter("codex")
    assert a.mcp_shape is McpShape.TOML_MCP_SERVERS


def test_continue_uses_yaml_shape() -> None:
    a = get_adapter("continue")
    assert a.mcp_shape is McpShape.YAML_MCP_SERVERS


def test_every_known_agent_has_an_adapter() -> None:
    ids = {a.agent_id for a in iter_adapters()}
    expected = {
        "claude-code",
        "opencode",
        "cursor",
        "codex",
        "windsurf",
        "vscode-copilot",
        "gemini-cli",
        "kilo-code",
        "kiro-ide",
        "qwen-code",
        "continue",
        "cline",
        "roo",
    }
    assert expected <= ids
