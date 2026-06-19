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


def test_initialize_without_sampling_does_not_register(server: MCPServer) -> None:
    assert get_host_sampler() is None
    server._handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}}
    )
    assert get_host_sampler() is None
