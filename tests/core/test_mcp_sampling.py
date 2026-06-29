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
    s = MCPServer(db_path=tmp_path / ".storage" / "opencontext" / "context_graph.db")
    # NOTE: opencontext_run not in safe default; sampling tests need it explicitly
    from opencontext_core.tools.policy import ToolPermissionPolicy

    s.policy = ToolPermissionPolicy(allowed_tools=set(s.tools.keys()))
    return s


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


def test_sampling_sends_per_role_model_as_preference_hint(
    server: MCPServer, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The per-role/per-phase model is forwarded to the client as an MCP
    # modelPreferences hint, so the client picks the matching model.
    response = json.dumps(
        {"jsonrpc": "2.0", "id": "oc-sampling-1", "result": {"content": {"text": "ok"}}}
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(response + "\n"))
    server._request_sampling("system", "design the module", 128, model="claude-opus-4")
    sent = capsys.readouterr().out
    assert "modelPreferences" in sent
    assert "claude-opus-4" in sent


def test_sampling_omits_hint_for_placeholder_model(
    server: MCPServer, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A placeholder model means "use the client's selected model" — send no hint.
    response = json.dumps(
        {"jsonrpc": "2.0", "id": "oc-sampling-1", "result": {"content": {"text": "ok"}}}
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(response + "\n"))
    server._request_sampling("system", "hi", 128, model="mock")
    sent = capsys.readouterr().out
    assert "modelPreferences" not in sent


def test_opencontext_run_requires_task(server: MCPServer) -> None:
    assert "error" in server._call_tool("opencontext_run", {})


def test_opencontext_run_drives_harness_with_host_sampler(
    server: MCPServer, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """C3 + PR-013: the in-process run tool drives the harness through the shared
    RuntimeApi and returns the full RunContract (not bare counts). The host
    sampler is live here (the standalone loop runs in a separate process)."""
    register_host_sampler(lambda s, p, n, m: "ok")

    captured: dict[str, str] = {}

    class _Result:
        run_id = "r1"
        status = "passed"

        def __init__(self) -> None:
            self.artifacts: list[object] = []
            self.gates: list[object] = []
            self.warnings: list[str] = []

    def _fake_run(self: object, workflow: str, task: str, *a: object, **k: object) -> _Result:
        captured["workflow"] = workflow
        captured["task"] = task
        return _Result()

    from opencontext_core.harness import runner as runner_mod

    monkeypatch.setattr(runner_mod.HarnessRunner, "run", _fake_run)
    # Pass an explicit root so the session tree is written under tmp, not cwd.
    out = server._call_tool(
        "opencontext_run", {"task": "do X", "workflow": "sdd", "root": str(tmp_path)}
    )

    assert captured == {"workflow": "sdd", "task": "do X"}
    assert out["status"] == "passed"
    data = out["data"]
    # PR-013 full contract keys are always present (even when empty).
    for key in (
        "session_id",
        "run_id",
        "workflow",
        "status",
        "summary",
        "artifacts",
        "receipts",
        "gates",
        "cost",
        "confidence",
        "next_recommended",
    ):
        assert key in data, f"missing run-contract key: {key}"
    assert data["host_model_used"] is True
    assert data["workflow"] == "sdd"
    assert data["session_id"].startswith("sess-")
    assert data["status"] in ("completed", "passed")


def test_initialize_without_sampling_does_not_register(server: MCPServer) -> None:
    assert get_host_sampler() is None
    server._handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}}
    )
    assert get_host_sampler() is None


def test_read_message_before_handles_batched_writes(
    server: MCPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two JSON-RPC messages written in ONE os.write must both be read. The old
    # select()+buffered-readline stranded the second line in the text buffer and
    # returned empty (turning a delivered sampling response into an empty answer).
    import os
    import time

    r, w = os.pipe()
    os.write(
        w,
        b'{"jsonrpc":"2.0","id":1,"method":"x"}\n'
        b'{"jsonrpc":"2.0","id":"oc-sampling-1","result":{"content":{"text":"ok"}}}\n',
    )
    os.close(w)
    monkeypatch.setattr(sys, "stdin", os.fdopen(r, "r"))
    first = server._read_message_before(time.monotonic() + 2)
    second = server._read_message_before(time.monotonic() + 2)
    assert first is not None and first["id"] == 1
    assert second is not None and second["id"] == "oc-sampling-1"
