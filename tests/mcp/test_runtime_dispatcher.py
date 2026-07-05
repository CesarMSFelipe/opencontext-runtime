"""Commit-008: MCP runtime.* dispatcher exposes all 9 session tools.

Per amendment A1, the MCP dispatcher registers EXACTLY these 9 tools (one
per RuntimeApi session method):

    runtime.start_session  -> api.start_session(StartSessionRequest)
    runtime.run            -> api.run(RunRequest)
    runtime.next           -> api.next(session_id)
    runtime.observe        -> api.observe(session_id, RuntimeEventInput)
    runtime.apply          -> api.apply(session_id, MutationRequest)
    runtime.inspect        -> api.inspect(session_id, InspectionScope)
    runtime.resume         -> api.resume(session_id)
    runtime.archive        -> api.archive(session_id)
    runtime.status         -> api.status(session_id)

Amendment A1 forbids ``runtime.run_workflow``: it MUST NOT be registered.
The dispatcher is gated by ``compat.is_migrated_flag("mcp-runtime")``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def _import_dispatcher():
    """Lazy import so test collection never touches the dispatcher module."""
    from opencontext_core.mcp import runtime_dispatcher as rd

    return rd


# ---------- 1. flag gate ----------------------------------------------------
def test_mcp_flag_off_uses_legacy() -> None:
    """``is_migrated_flag('mcp-runtime') is False`` -> no spine tools registered.

    The dispatcher exposes an empty/legacy tool set until the flag is on.
    """
    rd = _import_dispatcher()
    with patch("opencontext_core.compat.is_migrated_flag", return_value=False):
        tools = rd.registered_tools()
    # The runtime.* tools MUST NOT be present in legacy mode.
    for name in (
        "runtime.start_session",
        "runtime.run",
        "runtime.next",
        "runtime.observe",
        "runtime.apply",
        "runtime.inspect",
        "runtime.resume",
        "runtime.archive",
        "runtime.status",
    ):
        assert name not in tools, f"{name} MUST NOT be registered when mcp-runtime is off"


# ---------- 2. flag on -> 9 tools registered --------------------------------
def test_mcp_flag_on_uses_spine() -> None:
    """``is_migrated_flag('mcp-runtime') is True`` -> all 9 tools registered."""
    rd = _import_dispatcher()
    with patch("opencontext_core.compat.is_migrated_flag", return_value=True):
        tools = rd.registered_tools()
    expected = {
        "runtime.start_session",
        "runtime.run",
        "runtime.next",
        "runtime.observe",
        "runtime.apply",
        "runtime.inspect",
        "runtime.resume",
        "runtime.archive",
        "runtime.status",
    }
    missing = expected - set(tools)
    assert not missing, f"missing MCP session tools: {sorted(missing)}"


# ---------- 3. exactly 9 session tools ---------------------------------------
def test_all_nine_session_tools_registered() -> None:
    """The dispatcher exposes EXACTLY 9 ``runtime.*`` tools, no more, no less.

    Pins the 9-method session-first contract (amendment A1). A drift in
    count (8 or 10) fails the gate.
    """
    rd = _import_dispatcher()
    with patch("opencontext_core.compat.is_migrated_flag", return_value=True):
        tools = rd.registered_tools()
    session_tools = sorted(t for t in tools if t.startswith("runtime."))
    assert session_tools == sorted(
        [
            "runtime.apply",
            "runtime.archive",
            "runtime.inspect",
            "runtime.next",
            "runtime.observe",
            "runtime.resume",
            "runtime.run",
            "runtime.start_session",
            "runtime.status",
        ]
    ), session_tools


# ---------- 4. no run_workflow tool -----------------------------------------
def test_run_workflow_tool_absent() -> None:
    """``runtime.run_workflow`` is NOT a registered tool (amendment A1)."""
    rd = _import_dispatcher()
    with patch("opencontext_core.compat.is_migrated_flag", return_value=True):
        tools = rd.registered_tools()
    assert "runtime.run_workflow" not in tools


# ---------- 5. start_session delegates to RuntimeApi.start_session ---------
def test_start_session_delegates_to_runtime_api(tmp_path: Path) -> None:
    """``runtime.start_session`` calls ``RuntimeApi.start_session``.

    We mock RuntimeApi.start_session and assert the dispatcher passes the
    ``StartSessionRequest`` through unchanged.
    """
    from opencontext_core.runtime.api import SessionRef

    rd = _import_dispatcher()

    fake_session = SessionRef(session_id="sess-mcp", status="created", session_path=str(tmp_path))
    captured: dict[str, object] = {}

    class FakeApi:
        def __init__(self, *a: object, **kw: object) -> None:
            pass

        def start_session(self, request: object) -> object:
            captured["request"] = request
            return fake_session

    with patch("opencontext_core.compat.is_migrated_flag", return_value=True):
        with patch("opencontext_core.runtime.api.RuntimeApi", FakeApi):
            result = rd.handle_tool_call("runtime.start_session", {"task": "do x"})

    assert captured["request"] is not None
    assert getattr(captured["request"], "task", None) == "do x"
    assert result["session_id"] == "sess-mcp"


# ---------- 6. run() carries session_id from start_session -----------------
def test_run_carries_session_id() -> None:
    """``runtime.run`` extracts ``session_id`` from the request and forwards.

    The dispatcher is a thin pass-through; the routing identity (session_id)
    MUST be preserved end-to-end.
    """
    rd = _import_dispatcher()

    captured: dict[str, object] = {}

    class FakeApi:
        def __init__(self, *a: object, **kw: object) -> None:
            pass

        def run(self, request: object) -> object:
            captured["session_id"] = getattr(request, "session_id", None)
            captured["workflow_id"] = getattr(request, "workflow_id", None)
            # Return a minimal duck-typed RunResult.
            return type("R", (), {"run_id": "r1", "status": "completed"})()

    with patch("opencontext_core.compat.is_migrated_flag", return_value=True):
        with patch("opencontext_core.runtime.api.RuntimeApi", FakeApi):
            rd.handle_tool_call(
                "runtime.run",
                {"session_id": "sess-abc", "workflow_id": "oc-flow"},
            )

    assert captured["session_id"] == "sess-abc"
    assert captured["workflow_id"] == "oc-flow"
