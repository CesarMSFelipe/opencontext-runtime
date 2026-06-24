"""Prove the KG + 5-level memory MCP substrate returns REAL data in-process.

No MCP registration, no agent host, no stdio loop. This constructs ``MCPServer``
exactly the way the CLI does at ``main.py:_mcp_serve`` —

    runtime = OpenContextRuntime(storage_path=...)
    server  = MCPServer(db_path=..., runtime=runtime)

— against a small indexed tmp project, then calls the handlers directly via
``server._call_tool(...)`` and asserts the payloads are real, not empty and not a
degraded-error stub:

  * ``opencontext_context`` (the verified-context handler) returns a pack whose
    rendered context names the real ranked sources, with a real trace id and a
    non-zero token estimate — proving the KG + verified retrieval pipeline runs.
  * ``opencontext_memory_save`` returns an id + a concrete ``backend`` (NOT the
    "memory store unavailable" error), and ``opencontext_memory_search`` returns
    the just-saved record by id — proving the 5-level memory tools persist and
    recall against a live store.

The real returned payloads are printed (run with ``-s``) so the proof is visible.
This is the missing end-to-end link: the unit tests in ``test_mcp_memory_tools.py``
wire a *fake* runtime; here the runtime is the real one the CLI ships.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.mcp_stdio import MCPServer
from opencontext_core.runtime import OpenContextRuntime


def _cli_like_server(tmp_path: Path) -> tuple[MCPServer, OpenContextRuntime, Path]:
    """Build (server, runtime, project_root) the way ``main.py:_mcp_serve`` does.

    The CLI does ``OpenContextRuntime(storage_path=Path(db_path).parent)`` then
    ``MCPServer(db_path=db_path, runtime=runtime)``. The graph DB lives under the
    storage dir; the project root is whatever the installed config points at. We
    mirror a real install by pointing the runtime's configured project root at the
    indexed tmp project (this is what ``opencontext install`` writes into config),
    so the no-per-call-root MCP handler resolves to the right tree.
    """

    project = tmp_path / "proj"
    project.mkdir()
    (project / "auth.py").write_text(
        "def authenticate_user(token: str) -> bool:\n"
        "    '''Validate a session token.'''\n"
        "    return token == 'test-token'\n",
        encoding="utf-8",
    )
    (project / "login.py").write_text(
        "from auth import authenticate_user\n\n\n"
        "def login(token: str) -> str:\n"
        "    return 'ok' if authenticate_user(token) else 'deny'\n",
        encoding="utf-8",
    )
    (project / "billing.py").write_text(
        "def invoice(customer: str) -> int:\n    return 42\n",
        encoding="utf-8",
    )

    storage = tmp_path / ".storage" / "opencontext"
    db_path = storage / "context_graph.db"

    runtime = OpenContextRuntime(storage_path=storage)
    runtime.config.project_index.root = str(project)
    runtime.index_project(project)

    server = MCPServer(db_path=db_path, runtime=runtime)
    return server, runtime, project


class TestKgMemorySubstrateInProcess:
    def test_verified_context_handler_returns_real_pack(self, tmp_path: Path) -> None:
        """opencontext_context returns a real verified pack (sources + tokens + trace),
        not an empty string and not an error, with a real runtime attached."""

        server, _runtime, _project = _cli_like_server(tmp_path)
        try:
            result = server._call_tool(
                "opencontext_context",
                {"task": "Where is authenticate_user implemented and who calls it?"},
            )

            print("\n[substrate] opencontext_context payload (keys + summary):")
            summary = {k: result.get(k) for k in sorted(result)}
            print(json.dumps(summary, indent=2, default=str)[:2000])

            assert "error" not in result, f"verified-context handler errored: {result}"
            data = result.get("data", result)
            # Real verified pipeline shape (gates/trust/trace), not the raw fallback.
            assert data.get("trace_id"), "no trace id — pipeline did not run"
            assert data.get("trust_decision"), "no trust decision in verified result"
            context = data.get("context", "")
            assert isinstance(context, str) and context.strip(), "verified context is empty"
            # The KG ranked the real symbols: auth.py is the impl, login.py the caller.
            assert "auth.py" in context, f"expected auth.py in pack, got:\n{context}"
            assert "authenticate_user" in context, "expected the target symbol in the pack"
            assert "login.py" in context, "caller login.py should be surfaced by the call graph"
            # Real, non-zero token accounting.
            assert int(data.get("estimated_tokens", 0)) > 0, "pack reported zero tokens"
        finally:
            server.close()

    def test_memory_save_then_search_round_trip(self, tmp_path: Path) -> None:
        """opencontext_memory_save persists to the live 5-level store (id + backend,
        NOT 'memory store unavailable'); opencontext_memory_search recalls it."""

        server, _runtime, _project = _cli_like_server(tmp_path)
        try:
            saved = server._call_tool(
                "opencontext_memory_save",
                {
                    "content": (
                        "JWT bearer tokens authenticate login via authenticate_user in auth.py"
                    ),
                    "layer": "semantic",
                    "key": "auth:jwt-bearer",
                },
            )
            print("\n[substrate] opencontext_memory_save payload:")
            print(json.dumps(saved, indent=2, default=str))

            assert "error" not in saved, f"memory save degraded/errored: {saved}"
            saved_data = saved.get("data", saved)
            assert saved_data.get("id"), "memory save returned no id"
            assert saved_data.get("backend"), "memory save returned no backend (store not wired)"
            assert saved_data.get("layer") == "semantic"
            saved_id = saved_data["id"]

            found = server._call_tool(
                "opencontext_memory_search",
                {"query": "JWT bearer login authenticate"},
            )
            print("\n[substrate] opencontext_memory_search payload:")
            print(json.dumps(found, indent=2, default=str))

            assert "error" not in found, f"memory search errored: {found}"
            results = found.get("data", found).get("results", [])
            assert results, "memory search returned no records for a just-saved fact"
            ids = [r.get("id") for r in results]
            assert saved_id in ids, f"saved record {saved_id} not recalled; got ids {ids}"
            hit = next(r for r in results if r.get("id") == saved_id)
            assert "authenticate_user" in hit.get("content", "")
        finally:
            server.close()

    def test_substrate_is_the_live_cli_path_not_a_fake(self, tmp_path: Path) -> None:
        """Guard: the server actually carries a real OpenContextRuntime with a live
        memory store — i.e. this exercises the same wiring as main.py, not a stub."""

        server, runtime, _project = _cli_like_server(tmp_path)
        try:
            assert isinstance(server.runtime, OpenContextRuntime)
            assert server.runtime is runtime
            # The 5-level store the memory handlers reach through is real & present.
            assert getattr(runtime, "_v2_memory_store", None) is not None
        finally:
            server.close()
