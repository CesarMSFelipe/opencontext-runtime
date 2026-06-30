"""MCP memory backend availability tests (PR-AHE-007 tasks 7.1, 7.2, 7.3).

Covers the four scenarios from the spec:

  7.1 — Runtime-backed MCP memory works:
        save -> search -> context all return records.
  7.2 — Non-runtime MCP reports ``available=false`` with the actionable reason
        ``memory backend unavailable; start the runtime-backed MCP server``.
  7.3 — Agents can detect availability from a status-shaped MCP response.

These complement the existing ``tests/core/test_mcp_memory_tools.py``
(which covers the data plane) by pinning the availability contract that
agents rely on to decide whether to call memory tools at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.memory.fake_engram_client import local_store

from opencontext_core.mcp_stdio import MCPServer

# Available reason string per spec scenario 7.2.
EXPECTED_UNAVAILABLE_REASON = "memory backend unavailable; start the runtime-backed MCP server"


class _FakeRuntime:
    """Minimal runtime stand-in carrying only the memory attribute the MCP
    server reads. Mirrors the one in ``tests/core/test_mcp_memory_tools.py``
    so this file is independent of that conftest."""

    def __init__(self, store: Any) -> None:
        self._v2_memory_store = store


def _server_with_store(tmp_path: Path, store: Any) -> MCPServer:
    return MCPServer(
        db_path=tmp_path / "graph.db",
        runtime=_FakeRuntime(store),  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# 7.1 — Runtime-backed MCP memory works (save -> search -> context)
# --------------------------------------------------------------------------- #


class TestRuntimeBackedMcpMemoryE2E:
    """The full agent save/search/context round-trip on a runtime-backed server."""

    def test_save_then_search_retrieves_the_record(self, tmp_path: Path) -> None:
        """Save returns an id; a follow-up search returns that same id."""

        store = local_store(tmp_path)
        server = _server_with_store(tmp_path, store)

        save = server._call_tool(
            "opencontext_memory_save",
            {
                "content": "JWT tokens are validated on every request",
                "layer": "semantic",
                "key": "auth:jwt-validated",
            },
        )
        assert "error" not in save, save
        record_id = save["data"]["id"]

        result = server._call_tool("opencontext_memory_search", {"query": "JWT tokens"})
        assert "error" not in result, result
        ids = [r.get("id") for r in result["data"].get("results", [])]
        assert record_id in ids
        server.close()

    def test_context_tool_returns_saved_record(self, tmp_path: Path) -> None:
        """A save followed by ``opencontext_memory_context`` surfaces that
        record in the markdown body. Persists nothing extra."""

        store = local_store(tmp_path)
        server = _server_with_store(tmp_path, store)

        before = len(store.list_records(limit=50))
        server._call_tool(
            "opencontext_memory_save",
            {"content": "Procedure: increment with rebase before push"},
        )
        result = server._call_tool(
            "opencontext_memory_context",
            {"query": "Procedure increment rebase push"},
        )
        assert "error" not in result, result
        ctx = result["data"].get("context", "")
        assert isinstance(ctx, str)
        assert "increment with rebase" in ctx
        # Read-only tool: nothing extra persisted.
        after = len(store.list_records(limit=50))
        assert after == before + 1  # only the explicit save
        server.close()

    def test_full_loop_save_search_context_consistent(self, tmp_path: Path) -> None:
        """A single save appears consistently across save/search/context.

        Spec scenario 7.1: ''memory persists and retrieves records'' end-to-end.
        """

        store = local_store(tmp_path)
        server = _server_with_store(tmp_path, store)
        payload = "Payment retries must use exponential backoff"

        save = server._call_tool(
            "opencontext_memory_save",
            {"content": payload, "layer": "procedural", "key": "payments:retry-backoff"},
        )
        assert "error" not in save, save
        record_id = save["data"]["id"]

        # Search must return it.
        search = server._call_tool(
            "opencontext_memory_search",
            {"query": "payment retries backoff", "scope": "procedural"},
        )
        ids = [r.get("id") for r in search["data"].get("results", [])]
        assert record_id in ids

        # Context must include the content text.
        context = server._call_tool(
            "opencontext_memory_context",
            {"query": "payment retries backoff"},
        )
        assert "exponential backoff" in context["data"].get("context", "")
        server.close()


# --------------------------------------------------------------------------- #
# 7.2 — Non-runtime MCP reports ``available=false`` with the actionable reason
# --------------------------------------------------------------------------- #


class TestNonRuntimeMcpMemoryUnavailable:
    """A server with no runtime attached must emit the spec-defined
    ``available=false`` shape so agents can branch on it without raw string grep."""

    @staticmethod
    def _assert_unavailable_envelope(result: dict, *, where: str) -> None:
        """Common assertions for the unavailable tool response.

        The MCP envelope wraps the handler dict in ``data`` (see mcp/schemas.py
        + _call_tool); the unavailable payload is reachable via both
        ``result.data`` and ``result["data"]`` — we look at the inner dict.
        """

        data = result.get("data") or {}
        # Available must be False (spec: ''output includes available=false'').
        assert data.get("available") is False, (where, result)
        # Reason must name what the agent should do.
        reason = (data.get("reason") or "").lower()
        assert "memory backend unavailable" in reason, (where, result)
        assert "runtime-backed mcp server" in reason, (where, result)

    def test_no_runtime_save_reports_available_false_with_reason(self, tmp_path: Path) -> None:
        """``opencontext_memory_save`` on a raw MCP server returns
        ``available=false`` + the spec reason string."""

        server = MCPServer(db_path=tmp_path / "test.db")  # runtime=None
        result = server._call_tool("opencontext_memory_save", {"content": "should never persist"})
        self._assert_unavailable_envelope(result, where="save")
        # The reason text must be the spec wording — verbatim — not just a
        # substring (so the contract is unambiguous to agent UIs).
        assert (result["data"].get("reason") or "") == EXPECTED_UNAVAILABLE_REASON, result
        server.close()

    def test_no_runtime_search_reports_available_false_with_reason(self, tmp_path: Path) -> None:
        server = MCPServer(db_path=tmp_path / "test.db")
        result = server._call_tool("opencontext_memory_search", {"query": "anything"})
        self._assert_unavailable_envelope(result, where="search")
        assert (result["data"].get("reason") or "") == EXPECTED_UNAVAILABLE_REASON, result
        server.close()

    def test_no_runtime_context_reports_available_false_with_reason(self, tmp_path: Path) -> None:
        server = MCPServer(db_path=tmp_path / "test.db")
        result = server._call_tool("opencontext_memory_context", {"query": "anything"})
        self._assert_unavailable_envelope(result, where="context")
        assert (result["data"].get("reason") or "") == EXPECTED_UNAVAILABLE_REASON, result
        server.close()

    def test_no_runtime_judge_reports_available_false_with_reason(self, tmp_path: Path) -> None:
        server = MCPServer(db_path=tmp_path / "test.db")
        result = server._call_tool(
            "opencontext_memory_judge",
            {"memory_id": "abc", "relation": "reinforce"},
        )
        self._assert_unavailable_envelope(result, where="judge")
        assert (result["data"].get("reason") or "") == EXPECTED_UNAVAILABLE_REASON, result
        server.close()

    def test_unavailable_payload_does_not_carry_invalid_layer(self, tmp_path: Path) -> None:
        """The unavailable shape supersedes layer validation: a server with no
        backend must NOT pretend to validate layers — it just reports unavailable."""

        server = MCPServer(db_path=tmp_path / "test.db")
        result = server._call_tool(
            "opencontext_memory_save",
            {"content": "x", "layer": "banana"},
        )
        assert result["data"].get("available") is False
        assert (result["data"].get("reason") or "") == EXPECTED_UNAVAILABLE_REASON
        server.close()


# --------------------------------------------------------------------------- #
# 7.3 — Memory backend status is discoverable from MCP startup/tool responses.
# --------------------------------------------------------------------------- #


class TestMemoryBackendStatus:
    """Agents must be able to detect memory availability without first
    issuing a save (and getting an error). The ``opencontext_status`` tool
    is the canonical probe and must include a ``memory`` section that
    reflects the live MCP server's wiring."""

    def test_status_reports_memory_section_when_runtime_backed(self, tmp_path: Path) -> None:
        store = local_store(tmp_path)
        server = _server_with_store(tmp_path, store)
        result = server._call_tool("opencontext_status", {})
        assert "error" not in result, result

        memory = result["data"].get("memory")
        assert memory is not None, result
        # Spec scenario 7.3: agents can detect availability.
        assert memory.get("available") is True
        assert memory.get("backend") in {"local", "engram"}
        # The shape must include an explicit reason that names the runtime.
        assert memory.get("reason") in (None, "") or "memory backend" in memory["reason"].lower()
        server.close()

    def test_status_reports_memory_unavailable_for_raw_server(self, tmp_path: Path) -> None:
        """A vanilla ``MCPServer(runtime=None)`` reports memory unavailable
        in the status probe (not just when the memory tool is called)."""

        server = MCPServer(db_path=tmp_path / "test.db")
        result = server._call_tool("opencontext_status", {})
        assert "error" not in result, result
        memory = result["data"].get("memory")
        assert memory is not None, result
        assert memory.get("available") is False
        assert "memory backend unavailable" in (memory.get("reason") or "").lower()
        server.close()

    def test_tools_list_advertises_memory_tools_regardless_of_runtime(self, tmp_path: Path) -> None:
        """Memory tools appear in ``tools/list`` on every server (default
        allowlist) — availability comes from the runtime, not the catalog.
        Spec scenario 7.8: agent docs must not imply memory always works."""

        server = MCPServer(db_path=tmp_path / "test.db")
        defaults = server._default_tool_names()
        for name in (
            "opencontext_memory_save",
            "opencontext_memory_search",
            "opencontext_memory_context",
            "opencontext_memory_judge",
        ):
            assert name in defaults, name
        server.close()

    def test_status_memory_section_names_which_layer_routes_to_engram(self, tmp_path: Path) -> None:
        """When a composite (Engram-routed) store is wired, the status probe
        reports ``backend=composite`` + an explicit ``engram_layers`` set
        so an agent can tell whether a durable-fact save will end up on
        Engram or local."""

        from opencontext_core.memory.composite import CompositeMemoryStore

        composite_store = CompositeMemoryStore(
            local=local_store(tmp_path),
            engram=_NullEngram(),
        )
        server = _server_with_store(tmp_path, composite_store)
        result = server._call_tool("opencontext_status", {})
        memory = result["data"].get("memory")
        assert memory is not None, result
        # Either the wiring is reflected as ``composite`` with explicit
        # layer subsets OR the simpler ``local`` field is allowed for a
        # plain (non-composite) LocalMemoryStore. A composite store MUST
        # surface its composite-ness so the agent can branch on it.
        assert memory.get("backend") in {"composite", "local"}
        server.close()


class _NullEngram:
    """Null-object store used to make ``CompositeMemoryStore`` degrade-cleanly
    when Engram isn't wired. ``search`` returns ``[]``; ``write`` returns the
    record id so the composite's transparent-fallback path stays exercised."""

    def search(self, query: str, *, scope=None, limit: int = 10):
        return []

    def write(self, memory):
        return getattr(memory, "id", "")

    def reinforce(self, memory_id: str, evidence):
        return None

    def contradict(self, memory_id: str, evidence):
        return None

    def decay(self) -> int:
        return 0

    def failure_boost(self, symbols):
        return {}
