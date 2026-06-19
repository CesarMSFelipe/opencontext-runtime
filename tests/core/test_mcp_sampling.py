"""MCP server sampling transport — server uses the client's model, no provider."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from opencontext_core.llm.sampling_gateway import get_host_sampler, register_host_sampler
from opencontext_core.mcp_stdio import MCPServer


@pytest.fixture
def server(tmp_path: Path) -> MCPServer:
    return MCPServer(db_path=tmp_path / ".storage" / "opencontext" / "context_graph.db")


@pytest.fixture(autouse=True)
def _clear_sampler():
    yield
    register_host_sampler(None)


def test_request_sampling_round_trips_with_the_client(
    server: MCPServer, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The client answers the server's sampling/createMessage request.
    response = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "oc-sampling-1",
            "result": {"content": {"type": "text", "text": "HELLO FROM HOST MODEL"}},
        }
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(response + "\n"))

    out = server._request_sampling("be terse", "say hi", 128)

    assert out == "HELLO FROM HOST MODEL"
    sent = capsys.readouterr().out
    assert "sampling/createMessage" in sent  # server actually asked the client
    assert "say hi" in sent


def test_initialize_registers_host_sampler_when_client_supports_sampling(
    server: MCPServer,
) -> None:
    assert get_host_sampler() is None
    server._handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"capabilities": {"sampling": {}}},
        }
    )
    # The host model is now the agentic loop's gateway source — zero provider config.
    assert get_host_sampler() is not None


def test_request_sampling_returns_empty_when_host_never_answers(
    server: MCPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A host that advertises sampling but never replies must not deadlock.
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert server._request_sampling("be terse", "say hi", 128, timeout=0.5) == ""


def test_request_sampling_returns_empty_on_error_response(
    server: MCPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = json.dumps(
        {"jsonrpc": "2.0", "id": "oc-sampling-1", "error": {"code": -1, "message": "denied"}}
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(error + "\n"))
    assert server._request_sampling("be terse", "say hi", 128) == ""


def test_sampling_prompt_is_redacted_before_send(
    server: MCPServer, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "AKIAIOSFODNN7EXAMPLE"  # canonical AWS access-key shape
    response = json.dumps(
        {"jsonrpc": "2.0", "id": "oc-sampling-1", "result": {"content": {"text": "ok"}}}
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(response + "\n"))
    server._request_sampling("system", f"use key {secret} now", 128)
    sent = capsys.readouterr().out
    assert secret not in sent


def test_initialize_without_sampling_does_not_register(server: MCPServer) -> None:
    assert get_host_sampler() is None
    server._handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}}
    )
    assert get_host_sampler() is None
