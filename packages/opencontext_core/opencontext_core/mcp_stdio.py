"""MCP (Model Context Protocol) stdio transport server.

Implements the MCP protocol over stdio for agent integration.
Supports JSON-RPC 2.0 style communication.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from opencontext_core.indexing.call_graph import CallGraphAnalyzer
from opencontext_core.indexing.context_builder import ContextBuilder
from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.indexing.impact_analysis import ImpactAnalyzer
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.tools.policy import ToolPermissionPolicy

if TYPE_CHECKING:
    from opencontext_core.runtime import OpenContextRuntime


def _impact_risk_level(affected: int) -> str:
    """Derive a real risk level from impact blast-radius (never 'unknown')."""
    if affected >= 10:
        return "high"
    if affected >= 1:
        return "normal"
    return "low"


# Adaptive max_nodes tiers based on indexed file count
_MAX_NODES_TIERS: list[tuple[int, int]] = [
    (500, 10),
    (2000, 20),
    (10000, 40),
    (25000, 50),
]
_MAX_NODES_FALLBACK: int = 20
_MAX_NODES_MAX: int = 60


def _compute_max_nodes(file_count: int) -> int:
    """Compute max_nodes from indexed file count using tier table.

    Args:
        file_count: Number of indexed files.

    Returns:
        Scaled max_nodes value.
    """
    for threshold, value in _MAX_NODES_TIERS:
        if file_count < threshold:
            return value
    return _MAX_NODES_MAX


class MCPServer:
    """MCP server implementing stdio transport.

    Handles JSON-RPC style requests from AI agents for knowledge graph
    operations.
    """

    def __init__(
        self,
        db_path: str | Path = ".storage/opencontext/context_graph.db",
        policy: ToolPermissionPolicy | None = None,
        runtime: OpenContextRuntime | None = None,
    ) -> None:
        # When a runtime is provided, context/impact route through the verified
        # pipeline (gates/trust/trace). Without it, the legacy raw behavior is kept
        # for backward compatibility.
        self.runtime = runtime
        self.db = GraphDatabase(db_path=db_path)
        self.call_graph = CallGraphAnalyzer(db=self.db)
        self.impact = ImpactAnalyzer(db=self.db)
        self.context_builder = ContextBuilder(db_path=db_path)
        self.kg = KnowledgeGraph(db_path=db_path)
        # Permission gate: every tool call goes through ``policy.allows()``
        # before the handler runs. Default policy allowlists every tool the
        # server exposes; callers can tighten it via the constructor.
        self.policy: ToolPermissionPolicy = policy or ToolPermissionPolicy(
            allowed_tools=set(self._default_tool_names())
        )

        # Tool definitions
        self.tools: dict[str, dict[str, Any]] = {
            "opencontext_search": {
                "description": "Find symbols by name across the codebase",
                "parameters": {
                    "query": {"type": "string", "description": "Symbol name to search"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
            "opencontext_context": {
                "description": "Build relevant code context for a task",
                "parameters": {
                    "task": {"type": "string", "description": "Task description"},
                    "max_nodes": {"type": "integer", "default": 20},
                    "format": {"type": "string", "default": "markdown"},
                },
            },
            "opencontext_callers": {
                "description": "Find what calls a function",
                "parameters": {
                    "symbol": {"type": "string", "description": "Function/method name"},
                    "file": {"type": "string", "description": "File path (optional)"},
                    "depth": {"type": "integer", "default": 2},
                },
            },
            "opencontext_callees": {
                "description": "Find what a function calls",
                "parameters": {
                    "symbol": {"type": "string", "description": "Function/method name"},
                    "file": {"type": "string", "description": "File path (optional)"},
                    "depth": {"type": "integer", "default": 2},
                },
            },
            "opencontext_impact": {
                "description": "Analyze what code is affected by changing a symbol",
                "parameters": {
                    "symbol": {"type": "string", "description": "Symbol to analyze"},
                    "file": {"type": "string", "description": "File path (optional)"},
                    "radius": {"type": "integer", "default": 2},
                },
            },
            "opencontext_node": {
                "description": "Get details about a specific symbol",
                "parameters": {
                    "symbol": {"type": "string", "description": "Symbol name"},
                    "file": {"type": "string", "description": "File path (optional)"},
                },
            },
            "opencontext_files": {
                "description": "Get indexed file structure",
                "parameters": {
                    "filter": {"type": "string", "description": "Path filter (optional)"},
                    "max_depth": {"type": "integer", "default": 10},
                },
            },
            "opencontext_status": {
                "description": "Check index health and statistics",
                "parameters": {},
            },
            "opencontext_trace": {
                "description": "Find the shortest path between two symbols in the call graph",
                "parameters": {
                    "source": {"type": "string", "description": "Source symbol name"},
                    "target": {"type": "string", "description": "Target symbol name"},
                    "max_depth": {"type": "integer", "default": 10},
                },
            },
        }

    def run(self) -> None:
        """Run the MCP server, reading from stdin and writing to stdout."""

        # Send initialization notification
        self._send_notification("server/initialized", {"tools": list(self.tools.keys())})

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                self._send_error(None, -32700, "Parse error")
                continue

            self._handle_request(request)

    def _handle_request(self, request: dict[str, Any]) -> None:
        """Handle a single JSON-RPC request."""

        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        if method == "initialize":
            self._send_response(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "opencontext-mcp",
                        "version": "0.1.0",
                    },
                },
            )
            return

        if method == "tools/list":
            tools_list = [
                {
                    "name": name,
                    "description": info["description"],
                    "inputSchema": {
                        "type": "object",
                        "properties": info["parameters"],
                    },
                }
                for name, info in self.tools.items()
            ]
            self._send_response(request_id, {"tools": tools_list})
            return

        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_params = params.get("arguments", {})
            result = self._call_tool(tool_name, tool_params)
            self._send_response(request_id, result)
            return

        self._send_error(request_id, -32601, f"Method not found: {method}")

    def _call_tool(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call.

        Every tool call passes through :meth:`ToolPermissionPolicy.allows`
        before the handler runs. This is the single chokepoint for the
        9 MCP tools; the handler map below is only consulted if the
        policy allows the call.
        """

        # 1. Policy gate. No tool executes without a prior policy check.
        if not self.policy.allows(name):
            return {
                "error": f"Tool '{name}' denied by policy",
                "reason": "tool_not_allowlisted",
                "policy": "ToolPermissionPolicy",
            }

        handlers = self._handlers()

        handler = handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}

        try:
            return handler(params)
        except Exception as exc:
            return {"error": str(exc)}

    def _handlers(self) -> dict[str, Any]:
        """Return the mapping of tool name -> handler. Kept as a method so
        subclasses can override without forking :meth:`_call_tool`.

        The values are bound methods; we type them as ``Any`` because the
        return type is uniformly a ``dict[str, dict[str, Any]]`` to callers
        and a stricter type would not help callers either way.
        """

        return {
            "opencontext_search": self._handle_search,
            "opencontext_context": self._handle_context,
            "opencontext_callers": self._handle_callers,
            "opencontext_callees": self._handle_callees,
            "opencontext_impact": self._handle_impact,
            "opencontext_node": self._handle_node,
            "opencontext_files": self._handle_files,
            "opencontext_status": self._handle_status,
            "opencontext_trace": self._handle_trace,
        }

    def _default_tool_names(self) -> list[str]:
        """Tool names registered at construction time. Used as the default
        allowlist so a vanilla :class:`MCPServer` keeps working unchanged."""

        return [
            "opencontext_search",
            "opencontext_context",
            "opencontext_callers",
            "opencontext_callees",
            "opencontext_impact",
            "opencontext_node",
            "opencontext_files",
            "opencontext_status",
            "opencontext_trace",
        ]

    def _handle_search(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle search tool."""

        query = params.get("query", "")
        limit = params.get("limit", 20)

        results = self.db.search_fts(query, limit=limit)
        return {
            "results": [
                {
                    "name": r.get("name"),
                    "kind": r.get("kind"),
                    "file": r.get("file_path"),
                    "line": r.get("line"),
                    "score": r.get("rank"),
                }
                for r in results
            ]
        }

    def _verified_context(self, task: str) -> dict[str, Any]:
        """Build context through the runtime's verified pipeline (gates/trust/trace)."""

        from opencontext_core.retrieval.contracts import VerifiedContextRequest

        assert self.runtime is not None  # only called when a runtime is wired
        result = self.runtime.verify_context(VerifiedContextRequest(query=task))
        return {
            "context": result.context,
            "gates": [gate.model_dump(mode="json") for gate in result.gates],
            "risk_level": result.risk_level.value,
            "trust_decision": result.trust_decision.model_dump(mode="json"),
            "trace_id": result.trace_id,
            "estimated_tokens": result.token_usage.get("final_context_pack", 0),
        }

    def _handle_context(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle context building tool."""

        task = params.get("task", "")
        # Route through the verified pipeline when a runtime is wired (surface parity).
        if self.runtime is not None:
            return self._verified_context(task)

        max_nodes = params.get("max_nodes", 20)
        format = params.get("format", "markdown")

        # Adaptive scaling: when caller uses default (20), scale from stats
        if max_nodes == 20:
            try:
                stats = self.db.get_stats()
                file_count = stats.get("files", 0)
                max_nodes = _compute_max_nodes(file_count)
            except Exception:
                max_nodes = _MAX_NODES_FALLBACK

        context = self.context_builder.build_context(
            task=task,
            max_nodes=max_nodes,
            format=format,
        )
        rendered = self.context_builder.render(context)

        return {
            "context": rendered,
            "coverage": context.coverage,
            "estimated_tokens": context.total_tokens_estimate,
        }

    def _handle_callers(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle callers tool."""

        symbol = params.get("symbol", "")
        file = params.get("file")
        depth = params.get("depth", 2)

        # Find node
        node_id = self._find_node(symbol, file)
        if node_id is None:
            return {"error": f"Symbol not found: {symbol}"}

        callers = self.call_graph.get_callers(node_id, depth=depth)
        return {
            "symbol": symbol,
            "callers": [
                {
                    "name": c.get("name", ""),
                    "kind": c.get("kind", ""),
                    "file": c.get("file_path", ""),
                    "line": c.get("line", 0),
                }
                for c in callers
            ],
        }

    def _handle_callees(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle callees tool."""

        symbol = params.get("symbol", "")
        file = params.get("file")
        depth = params.get("depth", 2)

        node_id = self._find_node(symbol, file)
        if node_id is None:
            return {"error": f"Symbol not found: {symbol}"}

        callees = self.call_graph.get_callees(node_id, depth=depth)
        return {
            "symbol": symbol,
            "callees": [
                {
                    "name": c.get("name", ""),
                    "kind": c.get("kind", ""),
                    "file": c.get("file_path", ""),
                    "line": c.get("line", 0),
                }
                for c in callees
            ],
        }

    def _handle_impact(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle impact analysis tool."""

        symbol = params.get("symbol", "")
        file = params.get("file")
        radius = params.get("radius", 2)

        node_id = self._find_node(symbol, file)
        if node_id is None:
            return {"error": f"Symbol not found: {symbol}"}

        impact = self.impact.analyze(node_id, depth=radius)
        affected = len(impact.direct_callers) + len(impact.transitive_dependents)
        return {
            "symbol": symbol,
            "affected_nodes": affected,
            "affected_files": list(impact.affected_files),
            "test_files": list(impact.affected_tests),
            "risk_level": _impact_risk_level(affected),
        }

    def _handle_node(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle node details tool."""

        symbol = params.get("symbol", "")
        file = params.get("file")

        node_id = self._find_node(symbol, file)
        if node_id is None:
            return {"error": f"Symbol not found: {symbol}"}

        node = self.db.get_node_by_id(node_id)
        if node is None:
            return {"error": f"Node not found: {node_id}"}

        return {
            "name": node.name,
            "kind": node.kind,
            "file": node.file_path,
            "line": node.line,
            "column": node.column,
            "end_line": node.end_line,
            "language": node.language,
            "container": node.container,
            "docstring": node.docstring,
            "signature": node.signature,
            "is_exported": node.is_exported,
        }

    def _handle_files(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle file structure tool."""

        filter_pattern = params.get("filter")
        max_depth = params.get("max_depth", 10)

        conn = self.db._connect()
        if filter_pattern:
            cursor = conn.execute(
                "SELECT path, language FROM files WHERE path LIKE ? ORDER BY path LIMIT ?",
                (f"%{filter_pattern}%", 1000),
            )
        else:
            cursor = conn.execute(
                "SELECT path, language FROM files ORDER BY path LIMIT ?",
                (1000,),
            )

        files = []
        for row in cursor.fetchall():
            path = row[0]
            depth = len(Path(path).parts)
            if depth <= max_depth:
                files.append({"path": path, "language": row[1]})

        return {"files": files}

    def _handle_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle status tool."""

        stats = self.db.get_stats()
        return {
            "indexed": stats.get("nodes", 0) > 0,
            "nodes": stats.get("nodes", 0),
            "edges": stats.get("edges", 0),
            "files": stats.get("files", 0),
        }

    def _handle_trace(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle call-path tracing tool."""

        source = params.get("source", "")
        target = params.get("target", "")
        max_depth = params.get("max_depth", 10)

        if not source or not target:
            return {"error": "Both 'source' and 'target' are required"}

        source_id = self._find_node(source)
        target_id = self._find_node(target)

        if source_id is None:
            return {"error": f"Symbol not found: {source}", "code": "SYMBOL_NOT_FOUND"}
        if target_id is None:
            return {"error": f"Symbol not found: {target}", "code": "SYMBOL_NOT_FOUND"}

        result = self.call_graph.find_path(source_id, target_id, max_depth=max_depth)

        return {
            "found": result.found,
            "path": result.path,
            "depth_exceeded": result.depth_exceeded,
            "hops": result.hops,
        }

    def _find_node(self, symbol: str, file: str | None = None) -> int | None:
        """Find node ID by symbol name and optional file."""

        results = self.db.search_fts(symbol, limit=20)
        for result in results:
            if result.get("name") == symbol:
                if file is None or result.get("file_path") == file:
                    return result.get("id")
        return None

    def _send_response(self, request_id: Any, result: dict[str, Any]) -> None:
        """Send a JSON-RPC response."""

        response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        self._write_json(response)

    def _send_error(self, request_id: Any, code: int, message: str) -> None:
        """Send a JSON-RPC error."""

        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        self._write_json(response)

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification."""

        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        self._write_json(notification)

    @staticmethod
    def _write_json(data: dict[str, Any]) -> None:
        """Write JSON data to stdout with flush."""

        sys.stdout.write(json.dumps(data) + "\n")
        sys.stdout.flush()

    def close(self) -> None:
        """Close all resources."""

        self.db.close()
        self.context_builder.close()
