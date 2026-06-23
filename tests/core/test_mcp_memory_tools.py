"""Tests for the four ``opencontext_memory_*`` MCP tools (workstream A — PR4).

Covers the agent-driven write/read/curate path over the existing
``CompositeMemoryStore`` (reached via ``runtime._v2_memory_store``):

  * advertise + default-allowlist (A-REQ-1)
  * save -> EPISODIC default + id reporting (A-REQ-2/3)
  * explicit layer + round-trip via search (A-2b / A-5a)
  * invalid layer -> structured error, persists nothing (A-3b)
  * no store / no runtime -> structured error, never raises (A-REQ-4a)
  * Engram-less default-EPISODIC save -> no raise + backend reporting (A-4b / N3)
  * memory_context reads, persists nothing (A-5b)
  * memory_judge reinforce/contradict curate one record; bad verdict errors (A-5c / N2)

Plus the 4b proactive-save protocol render assertion (A-6a) and the
no-config-field assertion (A-6b).

The tests follow the existing ``tests/core/test_mcp_stdio.py`` patterns:
``MCPServer(db_path=tmp_path / "test.db")`` for the no-store case, and a tiny
fake runtime carrying ``_v2_memory_store`` for the wired case.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.mcp_stdio import MCPServer
from opencontext_core.memory.agent import NullAgentMemoryStore
from opencontext_core.memory.composite import CompositeMemoryStore
from opencontext_core.memory.graph import LocalMemoryStore

_MEMORY_TOOLS = (
    "opencontext_memory_save",
    "opencontext_memory_search",
    "opencontext_memory_context",
    "opencontext_memory_judge",
)


class _FakeRuntime:
    """Minimal stand-in carrying only what the memory handlers read."""

    def __init__(self, store: Any) -> None:
        self._v2_memory_store = store


def _local_store(tmp_path: Path) -> LocalMemoryStore:
    return LocalMemoryStore(tmp_path / "memory.db")


def _server_with_store(tmp_path: Path, store: Any) -> MCPServer:
    """A server whose runtime exposes ``store`` as ``_v2_memory_store``.

    The MCP graph DB is still a throwaway temp file; only the memory path is
    exercised here.
    """

    server = MCPServer(db_path=tmp_path / "graph.db", runtime=_FakeRuntime(store))  # type: ignore[arg-type]
    return server


# --------------------------------------------------------------------------- #
# A-REQ-1 — advertise + default allowlist
# --------------------------------------------------------------------------- #


class TestMemoryToolsAdvertised:
    def test_four_tools_registered_with_schemas(self, tmp_path: Path) -> None:
        server = MCPServer(db_path=tmp_path / "test.db")
        for name in _MEMORY_TOOLS:
            assert name in server.tools, f"{name} missing from tools dict"
            schema = server.tools[name]
            assert "description" in schema
            assert "parameters" in schema
        server.close()

    def test_four_tools_in_default_allowlist(self, tmp_path: Path) -> None:
        server = MCPServer(db_path=tmp_path / "test.db")
        names = server._default_tool_names()
        for name in _MEMORY_TOOLS:
            assert name in names
        server.close()

    def test_four_tools_have_handlers(self, tmp_path: Path) -> None:
        server = MCPServer(db_path=tmp_path / "test.db")
        handlers = server._handlers()
        for name in _MEMORY_TOOLS:
            assert name in handlers
        server.close()

    def test_default_policy_allows_memory_tools(self, tmp_path: Path) -> None:
        """A-1b: each memory tool passes ToolPermissionPolicy.allows() by default."""

        server = MCPServer(db_path=tmp_path / "test.db")
        for name in _MEMORY_TOOLS:
            assert server.policy.allows(name), f"{name} not allowed by default policy"
        server.close()

    def test_memory_tool_names_carry_prefix(self, tmp_path: Path) -> None:
        """D-REQ-3: every memory tool name carries the opencontext_ prefix."""

        server = MCPServer(db_path=tmp_path / "test.db")
        for name in _MEMORY_TOOLS:
            assert name.startswith("opencontext_")
        server.close()


# --------------------------------------------------------------------------- #
# A-REQ-2/3 — save persists + EPISODIC default
# --------------------------------------------------------------------------- #


class TestMemorySave:
    def test_minimal_save_defaults_to_episodic(self, tmp_path: Path) -> None:
        """A-2a / A-3a: content-only save persists with layer EPISODIC and reports id."""

        server = _server_with_store(tmp_path, _local_store(tmp_path))
        result = server._call_tool(
            "opencontext_memory_save",
            {"content": "JWT tokens are used for login auth"},
        )
        assert "error" not in result, result
        assert result.get("layer") == "episodic"
        assert result.get("id")
        server.close()

    def test_explicit_layer_and_key_round_trips_via_search(self, tmp_path: Path) -> None:
        """A-2b / A-5a: explicit layer + key persists and is retrievable by search."""

        store = _local_store(tmp_path)
        server = _server_with_store(tmp_path, store)
        save = server._call_tool(
            "opencontext_memory_save",
            {
                "content": "Race condition in the payment retry loop",
                "layer": "failure",
                "key": "payment:retry-race",
            },
        )
        assert "error" not in save, save
        assert save.get("layer") == "failure"
        saved_id = save["id"]

        found = server._call_tool(
            "opencontext_memory_search",
            {"query": "payment retry race"},
        )
        assert "error" not in found, found
        ids = [r.get("id") for r in found.get("results", [])]
        assert saved_id in ids
        server.close()

    def test_save_reports_record_id_distinct_per_call(self, tmp_path: Path) -> None:
        """DR3: default key must be unique-ish — two content-only saves do not collide."""

        store = _local_store(tmp_path)
        server = _server_with_store(tmp_path, store)
        a = server._call_tool("opencontext_memory_save", {"content": "same text"})
        b = server._call_tool("opencontext_memory_save", {"content": "same text"})
        assert a["id"] != b["id"]
        # both persisted (no silent topic-key upsert/overwrite)
        listed = store.list_records(limit=50)
        assert len({r.id for r in listed}) >= 2
        server.close()


# --------------------------------------------------------------------------- #
# A-REQ-3 — invalid layer rejected, persists nothing
# --------------------------------------------------------------------------- #


class TestMemorySaveInvalidLayer:
    def test_invalid_layer_returns_structured_error(self, tmp_path: Path) -> None:
        store = _local_store(tmp_path)
        server = _server_with_store(tmp_path, store)
        result = server._call_tool(
            "opencontext_memory_save",
            {"content": "x", "layer": "banana"},
        )
        assert "error" in result
        # names the allowed layers
        err = result["error"].lower()
        assert "episodic" in err and "failure" in err
        server.close()

    def test_invalid_layer_persists_nothing(self, tmp_path: Path) -> None:
        store = _local_store(tmp_path)
        server = _server_with_store(tmp_path, store)
        server._call_tool("opencontext_memory_save", {"content": "x", "layer": "banana"})
        assert store.list_records(limit=10) == []
        server.close()


# --------------------------------------------------------------------------- #
# A-REQ-4a — degrade cleanly with no store / no runtime
# --------------------------------------------------------------------------- #


class TestMemoryToolsDegradeNoStore:
    def test_no_runtime_each_tool_returns_error_not_raise(self, tmp_path: Path) -> None:
        """A-4a: a vanilla server (runtime=None) never raises; returns structured error."""

        server = MCPServer(db_path=tmp_path / "test.db")  # runtime=None
        calls = {
            "opencontext_memory_save": {"content": "x"},
            "opencontext_memory_search": {"query": "x"},
            "opencontext_memory_context": {"query": "x"},
            "opencontext_memory_judge": {"memory_id": "abc", "relation": "reinforce"},
        }
        for name, params in calls.items():
            result = server._call_tool(name, params)
            assert "error" in result, f"{name} should degrade with an error"
            assert "unavailable" in result["error"].lower()
        server.close()

    def test_runtime_present_but_store_absent_degrades(self, tmp_path: Path) -> None:
        """Runtime attached but no ``_v2_memory_store`` -> structured error, no raise."""

        class _NoStoreRuntime:
            pass

        server = MCPServer(
            db_path=tmp_path / "test.db",
            runtime=_NoStoreRuntime(),  # type: ignore[arg-type]
        )
        result = server._call_tool("opencontext_memory_save", {"content": "x"})
        assert "error" in result
        assert "unavailable" in result["error"].lower()
        server.close()


# --------------------------------------------------------------------------- #
# A-REQ-4b / N3 — Engram-less default-EPISODIC save + backend reporting
# --------------------------------------------------------------------------- #


class TestMemorySaveBackendReporting:
    def test_engramless_default_episodic_does_not_raise(self, tmp_path: Path) -> None:
        """A-4b: EPISODIC routes to engram, but an Engram-less composite must not fail."""

        composite = CompositeMemoryStore(
            local=_local_store(tmp_path),
            engram=NullAgentMemoryStore(),
        )
        server = _server_with_store(tmp_path, composite)
        result = server._call_tool("opencontext_memory_save", {"content": "durable fact"})
        assert "error" not in result, result
        assert result.get("layer") == "episodic"
        server.close()

    def test_engramless_save_reports_degraded_local_backend(self, tmp_path: Path) -> None:
        """N3 / TR4: Engram-owned layer with no engram reports backend=local, degraded."""

        composite = CompositeMemoryStore(
            local=_local_store(tmp_path),
            engram=NullAgentMemoryStore(),
        )
        server = _server_with_store(tmp_path, composite)
        result = server._call_tool("opencontext_memory_save", {"content": "durable fact"})
        assert result.get("backend") == "local"
        assert result.get("degraded") is True
        server.close()

    def test_local_layer_is_not_degraded(self, tmp_path: Path) -> None:
        """A FAILURE-layer save (local-owned) is never marked degraded."""

        composite = CompositeMemoryStore(
            local=_local_store(tmp_path),
            engram=NullAgentMemoryStore(),
        )
        server = _server_with_store(tmp_path, composite)
        result = server._call_tool(
            "opencontext_memory_save",
            {"content": "a failing pattern", "layer": "failure"},
        )
        assert result.get("backend") == "local"
        assert result.get("degraded") is False
        server.close()

    def test_plain_local_store_reports_local_backend(self, tmp_path: Path) -> None:
        """A non-composite LocalMemoryStore reports backend=local (and not degraded)."""

        server = _server_with_store(tmp_path, _local_store(tmp_path))
        result = server._call_tool("opencontext_memory_save", {"content": "fact"})
        assert result.get("backend") == "local"
        assert result.get("degraded") is False
        server.close()


# --------------------------------------------------------------------------- #
# A-REQ-5 — search / context / judge
# --------------------------------------------------------------------------- #


class TestMemorySearchContext:
    def test_search_scope_filter(self, tmp_path: Path) -> None:
        store = _local_store(tmp_path)
        server = _server_with_store(tmp_path, store)
        server._call_tool(
            "opencontext_memory_save",
            {"content": "failure scoped record", "layer": "failure"},
        )
        server._call_tool(
            "opencontext_memory_save",
            {"content": "procedural scoped record", "layer": "procedural"},
        )
        scoped = server._call_tool(
            "opencontext_memory_search",
            {"query": "scoped record", "scope": "failure"},
        )
        assert "error" not in scoped, scoped
        layers = {r.get("layer") for r in scoped.get("results", [])}
        assert layers <= {"failure"}
        server.close()

    def test_invalid_scope_returns_error(self, tmp_path: Path) -> None:
        server = _server_with_store(tmp_path, _local_store(tmp_path))
        result = server._call_tool(
            "opencontext_memory_search",
            {"query": "x", "scope": "banana"},
        )
        assert "error" in result
        server.close()

    def test_context_returns_markdown_and_persists_nothing(self, tmp_path: Path) -> None:
        """A-5b: memory_context returns formatted context and writes nothing new."""

        store = _local_store(tmp_path)
        server = _server_with_store(tmp_path, store)
        server._call_tool(
            "opencontext_memory_save",
            {"content": "context probe about caching layers"},
        )
        before = len(store.list_records(limit=50))
        ctx = server._call_tool("opencontext_memory_context", {"query": "caching layers"})
        assert "error" not in ctx, ctx
        # context is returned as a markdown string
        assert isinstance(ctx.get("context"), str)
        assert "caching layers" in ctx["context"]
        after = len(store.list_records(limit=50))
        assert after == before  # no new write
        server.close()


class TestMemoryJudge:
    def _save(self, server: MCPServer) -> str:
        result = server._call_tool(
            "opencontext_memory_save",
            {"content": "belief under judgement", "layer": "failure"},
        )
        return str(result["id"])

    def test_reinforce_curates_one_record(self, tmp_path: Path) -> None:
        store = _local_store(tmp_path)
        server = _server_with_store(tmp_path, store)
        mem_id = self._save(server)
        before = len(store.list_records(limit=50))
        result = server._call_tool(
            "opencontext_memory_judge",
            {"memory_id": mem_id, "relation": "reinforce"},
        )
        assert "error" not in result, result
        after = len(store.list_records(limit=50))
        assert after == before  # nothing created or deleted
        server.close()

    def test_contradict_curates_one_record(self, tmp_path: Path) -> None:
        store = _local_store(tmp_path)
        server = _server_with_store(tmp_path, store)
        mem_id = self._save(server)
        before = len(store.list_records(limit=50))
        result = server._call_tool(
            "opencontext_memory_judge",
            {"memory_id": mem_id, "relation": "contradict"},
        )
        assert "error" not in result, result
        after = len(store.list_records(limit=50))
        assert after == before
        server.close()

    def test_unknown_relation_returns_structured_error(self, tmp_path: Path) -> None:
        """N2: only reinforce/contradict are exposed; anything else is an error."""

        server = _server_with_store(tmp_path, _local_store(tmp_path))
        result = server._call_tool(
            "opencontext_memory_judge",
            {"memory_id": "abc", "relation": "supersede"},
        )
        assert "error" in result
        err = result["error"].lower()
        assert "reinforce" in err and "contradict" in err
        server.close()


# --------------------------------------------------------------------------- #
# A-REQ-6 — proactive-save protocol in the managed instruction block (4b)
# --------------------------------------------------------------------------- #


class TestProactiveSaveProtocol:
    def test_default_instructions_name_the_four_tools(self) -> None:
        from opencontext_core.configurator.service import _default_instructions

        text = _default_instructions("claude-code")
        for name in _MEMORY_TOOLS:
            assert name in text, f"{name} not referenced in managed instructions"

    def test_default_instructions_carry_layer_guidance(self) -> None:
        from opencontext_core.configurator.service import _default_instructions

        text = _default_instructions("claude-code")
        assert "FAILURE" in text
        assert "SEMANTIC" in text
        assert "PROCEDURAL" in text
        assert "EPISODIC" in text

    def test_protocol_is_inside_a_section_not_a_config_field(self) -> None:
        """A-6b: the protocol is instruction text; no proactive-save config field exists."""

        from opencontext_core.config import OpenContextConfig, default_config_data

        cfg = OpenContextConfig(**default_config_data())
        dumped = cfg.model_dump()
        flat = str(dumped).lower()
        assert "proactive_save" not in flat
        assert "proactive-save" not in flat

    def test_orchestrator_persona_points_at_memory_tools(self) -> None:
        """A-T5: the OC Orchestrator persona prompt carries a one-line pointer."""

        from opencontext_core.personas import get_persona

        orch = get_persona("oc-orchestrator")
        assert orch is not None
        assert "opencontext_memory_save" in orch.system_prompt
