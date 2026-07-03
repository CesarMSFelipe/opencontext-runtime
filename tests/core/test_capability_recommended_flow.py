"""Tests for ClientCapability recommended_flow field."""

from __future__ import annotations

from opencontext_core.configurator.capability import build_capability_matrix


def test_claude_code_recommended_flow():
    matrix = build_capability_matrix()
    cap = matrix.get("claude-code")
    assert cap is not None
    assert cap.recommended_flow == "native_oc_new"
    assert cap.supports_slash_commands is True
    assert cap.supports_subagents is True
    assert cap.supports_hooks is True


def test_aider_recommended_flow():
    matrix = build_capability_matrix()
    cap = matrix.get("aider")
    assert cap is not None
    assert cap.recommended_flow == "instructions_only"
    assert cap.supports_subagents is False


def test_opencode_recommended_flow():
    matrix = build_capability_matrix()
    cap = matrix.get("opencode")
    assert cap is not None
    assert cap.recommended_flow == "mcp_run"
    # opencode 1.17.12 does not advertise `sampling` at MCP initialize;
    # runtime capability detection upgrades automatically if that changes.
    assert cap.supports_sampling is False
    assert cap.supports_slash_commands is False


def test_codex_recommended_flow():
    matrix = build_capability_matrix()
    cap = matrix.get("codex")
    assert cap is not None
    assert cap.recommended_flow == "cli_loop"


def test_all_clients_have_recommended_flow():
    matrix = build_capability_matrix()
    for cap in matrix.clients:
        assert cap.recommended_flow in {
            "native_oc_new",
            "mcp_run",
            "cli_loop",
            "instructions_only",
        }, f"{cap.agent_id} has invalid recommended_flow: {cap.recommended_flow}"
