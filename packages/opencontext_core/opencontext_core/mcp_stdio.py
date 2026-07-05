"""MCP (Model Context Protocol) stdio transport server.

Implements the MCP protocol over stdio for agent integration.
Supports JSON-RPC 2.0 style communication.
"""

from __future__ import annotations

import json
import os
import re
import select
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from opencontext_core.configurator.filemerge import write_text_atomic
from opencontext_core.indexing.call_graph import CallGraphAnalyzer
from opencontext_core.indexing.context_builder import ContextBuilder
from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.indexing.impact_analysis import ImpactAnalyzer
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.tools.policy import ToolPermissionPolicy

if TYPE_CHECKING:
    from opencontext_core.indexing.graph_db import Node
    from opencontext_core.runtime import OpenContextRuntime
    from opencontext_core.runtime.api import RuntimeApi


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


def _replace_identifier(line: str, old: str, new: str) -> tuple[str, int]:
    """Replace whole-word occurrences of ``old`` with ``new`` on a single line.

    Word boundaries keep ``audit_login`` from matching inside ``audit_login_v2``
    or ``my_audit_login``. Returns the rewritten line and the number of hits.
    """

    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])")
    return pattern.subn(new, line)


def _split_lines(text: str) -> tuple[list[str], bool]:
    """Split source into lines without keepends, tracking a trailing newline.

    Returns ``(lines, trailing_newline)``. Re-joining with ``"\\n"`` and adding a
    final newline iff ``trailing_newline`` round-trips the original byte content.
    """

    trailing = text.endswith("\n")
    body = text[:-1] if trailing else text
    lines = body.split("\n") if body else []
    return lines, trailing


def _join_lines(lines: list[str], trailing_newline: bool) -> str:
    """Inverse of :func:`_split_lines`."""

    text = "\n".join(lines)
    if trailing_newline and (text or lines):
        text += "\n"
    return text


def _sdd_run_metadata(legacy: Any, workflow: str) -> dict[str, Any]:
    """Small MCP-only phase summary for SDD harness runs."""

    events = getattr(legacy, "events", []) or []
    phase_status: dict[str, str] = {}
    for event in events:
        if getattr(event, "action", None) == "run_phase":
            phase_status[str(getattr(event, "phase", ""))] = str(getattr(event, "status", ""))
    return {
        "selected_workflow": workflow,
        "phases": list(phase_status),
        "phase_status": phase_status,
        "verified_by": None,
        "verification_outcome": phase_status.get("verify"),
        "reason": getattr(legacy, "summary", "") or "",
    }


_IMPORT_LINE_RE = re.compile(r"^\s*(?:from\s+\S+\s+import|import)\b")


def _python_syntax_error(file_path: str, text: str) -> str | None:
    """For a ``.py`` file, return a message if ``text`` is not parseable, else None.

    The symbol-edit tools fail closed: an edit that would leave the file
    syntactically broken is rejected rather than written, so an agent can't
    silently corrupt source (e.g. replacing a whole def with only its body).
    """

    if not file_path.endswith(".py"):
        return None
    import ast

    try:
        ast.parse(text)
    except SyntaxError as exc:
        return f"invalid Python after edit: {exc.msg} (line {exc.lineno})"
    return None


def _to_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    """Wrap a tool's domain dict in the MCP ``tools/call`` content envelope.

    Spec-strict hosts (Claude Code, VS Code) require a ``content`` array; a raw
    domain dict placed directly in the JSON-RPC ``result`` reads as an empty tool
    response. The structured payload is preserved under ``structuredContent`` for
    clients that consume it, and a handler ``error`` maps to ``isError``.
    """

    from opencontext_core.safety.secrets import SecretScanner

    is_error = "error" in result
    # Redact secrets before anything crosses to the host — the "redaction is
    # automatic" guarantee. Redact the serialized form and re-parse so the
    # structured payload is scrubbed too; fall back to the raw dict if the
    # redacted text no longer parses.
    text = SecretScanner().redact(json.dumps(result, indent=2))
    try:
        structured = json.loads(text)
    except json.JSONDecodeError:
        structured = result
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
        "structuredContent": structured,
    }


# --------------------------------------------------------------------------- #
# Per-tool output schemas (workstream C3).
#
# Every tool's structured result is an object. On the failure/denied path
# ``_call_tool`` returns a ToolResultEnvelope (schema_version/tool/status/
# warnings/policy) plus the back-compat ``error``/``reason`` keys; on success a
# handler returns its own domain dict. A single rigid schema can't describe both
# arms, so each tool advertises a PERMISSIVE object schema: documented top-level
# keys (optional, no ``required``) for discoverability, with
# ``additionalProperties: true`` so neither the success dict nor the envelope is
# rejected. Honest metadata, not a contract the handlers would have to be
# rewritten to satisfy.
# --------------------------------------------------------------------------- #

# Envelope/error keys that any tool may return on the failure path.
_ENVELOPE_OUTPUT_KEYS: tuple[str, ...] = (
    "schema_version",
    "tool",
    "status",
    "warnings",
    "policy",
    "error",
    "reason",
)

# Conservative top-level success keys per tool (additionalProperties covers the
# nested detail). Derived from each handler's return shape.
_TOOL_SUCCESS_KEYS: dict[str, tuple[str, ...]] = {
    "opencontext_search": ("results", "count"),
    "opencontext_context": ("context", "estimated_tokens", "coverage", "symbol"),
    "opencontext_callers": ("callers", "symbol", "file"),
    "opencontext_callees": ("callees", "symbol", "file"),
    "opencontext_impact": (
        "symbol",
        "affected_files",
        "affected_nodes",
        "risk_level",
        "centrality",
        "test_files",
    ),
    "opencontext_node": ("name", "kind", "file", "line", "signature", "docstring", "container"),
    "opencontext_files": ("indexed", "files", "nodes", "edges", "languages", "directories"),
    "opencontext_status": ("indexed", "nodes", "edges", "files"),
    "opencontext_trace": ("found", "path", "hops", "code", "depth_exceeded"),
    "opencontext_quality": ("diff",),
    "opencontext_replace_symbol_body": (
        "applied",
        "symbol",
        "file",
        "changed_range",
        "approval_required",
        "hint",
    ),
    "opencontext_insert_before_symbol": ("applied", "symbol", "file", "approval_required", "hint"),
    "opencontext_insert_after_symbol": ("applied", "symbol", "file", "approval_required", "hint"),
    "opencontext_rename_symbol": ("applied", "symbol", "file", "new_name", "approval_required"),
    "opencontext_run": (
        "schema_version",
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
        "warnings",
        "host_model_used",
    ),
    "opencontext_session_start": ("session_id", "status", "session_path"),
    "opencontext_session_next": ("kind", "node_id", "reason"),
    "opencontext_session_observe": ("session_id", "status", "node", "last_event_id"),
    "opencontext_session_apply": ("applied", "status", "reason"),
    "opencontext_session_inspect": ("session_id", "status", "run_count", "event_count"),
    "opencontext_session_status": ("session_id", "status", "active_run_id"),
    "opencontext_session_resume": ("session_id", "status", "last_event_id"),
    "opencontext_session_archive": ("session_id", "archived", "status"),
    "opencontext_workflow_list": ("workflows",),
    "opencontext_workflow_explain": ("id", "when", "cost", "phases", "harnesses"),
    "opencontext_profile_list": ("config_profiles", "model_profiles"),
    "opencontext_profile_explain": ("id", "family", "security", "approvals"),
    "opencontext_doctor": ("ok", "failed", "findings"),
    "opencontext_memory_save": (
        "id",
        "layer",
        "key",
        "backend",
        "degraded",
        "run_id",
        "provenance",
    ),
    "opencontext_memory_search": ("results", "count"),
    "opencontext_memory_context": ("context", "count"),
    "opencontext_memory_judge": ("id", "relation", "ok"),
}

# Workflow tools unlocked by the ``allow_workflow_tools`` opt-in (the
# ``opencontext mcp --workflow-tools`` flag configured agents launch with).
# These drive OC Flow / SDD runs and the agent_execute follow-up; they write
# session state and run receipts, never source files directly — the
# symbol-write tools stay behind their own explicit policy opt-in.
WORKFLOW_TOOL_NAMES: tuple[str, ...] = (
    "opencontext_run",
    "opencontext_session_start",
    "opencontext_session_next",
    "opencontext_session_observe",
    "opencontext_session_apply",
    "opencontext_session_resume",
    "opencontext_session_archive",
)


def _tool_output_schema(name: str) -> dict[str, Any]:
    """Permissive per-tool output schema for ``tools/list`` (C3).

    Documents the keys a tool may return (success keys + envelope/error keys) as
    optional properties; ``additionalProperties: true`` keeps both response arms
    valid.
    """
    keys = (*_TOOL_SUCCESS_KEYS.get(name, ()), *_ENVELOPE_OUTPUT_KEYS)
    # Each documented key accepts any type (the value here is "this key appears",
    # not its exact shape — that stays open for handler freedom).
    properties: dict[str, dict[str, Any]] = {key: {} for key in keys}
    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }


# --------------------------------------------------------------------------- #
# Memory tools (workstream A) — agent-driven write/read/curate over the
# existing CompositeMemoryStore reached as ``runtime._v2_memory_store``.
# --------------------------------------------------------------------------- #

# Curation verbs the memory store actually exposes (composite.py:71/76). The
# ``opencontext_memory_judge`` tool is a thin dispatcher over exactly these — it
# does NOT invent judge/supersede verbs (design N2).
_JUDGE_RELATIONS: tuple[str, ...] = ("reinforce", "contradict")

# Default layer for a save when the caller omits ``layer`` (RD3).
_DEFAULT_MEMORY_LAYER_VALUE = "episodic"

# Spec scenario 7.2 — the wording agents parse off the unavailable response.
# Centralized here so every memory handler emits the same exact string and the
# docs/tests can pin it verbatim.
_MEMORY_UNAVAILABLE_REASON = "memory backend unavailable; start the runtime-backed MCP server"


def _memory_unavailable_envelope() -> dict[str, Any]:
    """The structured ``available=false`` response every memory handler
    returns when the runtime is not attached (or the memory store is None).

    Centralized so the shape stays stable: ``available=False``, the actionable
    ``reason`` string, and a backwards-compatible ``error`` key with the same
    text so older callers (and the test in
    ``test_mcp_safe_defaults.py``) that grep ``error`` keep working.
    """

    return {
        "error": _MEMORY_UNAVAILABLE_REASON,
        "available": False,
        "reason": _MEMORY_UNAVAILABLE_REASON,
    }


def _is_composite_store(store: Any) -> bool:
    """True when ``store`` is a ``CompositeMemoryStore`` (has an engram leg).

    Used by the status probe to surface composite routing to agents without
    coupling the test surface to the class identity directly.
    """

    return hasattr(store, "_engram") and hasattr(store, "_local")


def _local_layer_values() -> set[str]:
    """Layer values routed to the local store (single source of truth)."""

    from opencontext_core.memory.composite import _LOCAL_LAYERS

    return {layer.value for layer in _LOCAL_LAYERS}


def _make_memory_record(params: dict[str, Any]) -> Any:
    """Build a ``MemoryRecord`` from ``opencontext_memory_save`` params (A-T2).

    ``layer`` is optional and defaults to EPISODIC (RD3). The default ``key`` is a
    generated, unique handle (uuid-derived) and ``topic_key`` is left ``None``
    unless the caller supplies one, so a content-only save never silently upserts
    over an existing topic (DR3). An invalid ``layer`` raises ``ValueError`` naming
    the allowed layers; the handler converts that to a structured error result and
    persists nothing (A-REQ-3).
    """

    import uuid
    from datetime import UTC, datetime

    from opencontext_core.models.agent_memory import (
        DecayPolicy,
        MemoryLayer,
        MemoryRecord,
    )

    layer_value = params.get("layer") or _DEFAULT_MEMORY_LAYER_VALUE
    try:
        layer = MemoryLayer(layer_value)
    except ValueError as exc:
        allowed = ", ".join(m.value for m in MemoryLayer)
        raise ValueError(f"invalid layer {layer_value!r}; allowed layers: {allowed}") from exc

    content = str(params.get("content", ""))
    # Unique-ish default key so two content-only saves never collide / upsert.
    key = params.get("key") or f"agent:{layer.value}:{uuid.uuid4().hex[:12]}"
    confidence = params.get("confidence", 1.0)
    tags = params.get("tags") or []
    now = datetime.now(UTC)

    # Provenance (G): link a memory back to the run that produced it and record
    # how it was created. Optional — a content-only save still works unchanged.
    run_id = params.get("run_id")
    provenance = params.get("provenance")

    return MemoryRecord(
        id=uuid.uuid4().hex,
        layer=layer,
        key=str(key),
        content=content,
        confidence=float(confidence),
        decay_policy=DecayPolicy(enabled=True),
        tags=list(tags),
        created_at=now,
        updated_at=now,
        # topic_key stays None unless the caller asked for topic-keyed upsert.
        topic_key=params.get("topic_key"),
        run_id=str(run_id) if run_id is not None else None,
        provenance=str(provenance) if provenance is not None else None,
    )


def _engram_layer_values() -> set[str]:
    """The Engram-routed layer values, single-sourced from CompositeMemoryStore.

    Reading ``_ENGRAM_LAYERS`` (composite.py:21) rather than re-hardcoding the
    split keeps backend reporting honest if the routing rule ever changes
    (N3 / TR4).
    """

    from opencontext_core.memory.composite import _ENGRAM_LAYERS

    return {layer.value for layer in _ENGRAM_LAYERS}


def _store_has_live_engram(store: Any) -> bool:
    """True when ``store`` is a composite with a real (non-Null) engram backend.

    Used to decide whether an Engram-owned layer actually persisted to Engram or
    transparently fell back to local (composite.py:62-68).
    """

    engram = getattr(store, "_engram", None)
    if engram is None:
        return False
    return type(engram).__name__ != "NullAgentMemoryStore"


def _resolve_backend(store: Any, layer_value: str) -> tuple[str, bool]:
    """Return ``(backend, degraded)`` for a save of ``layer_value`` to ``store``.

    ``backend`` is ``"engram"`` only when the layer is Engram-owned AND the store
    has a live engram; otherwise ``"local"``. ``degraded`` is True only for the
    *transparent-fallback* case: a composite store whose Engram-owned layer fell
    back to local because no live engram is wired (composite.py:62-68 / A-REQ-4b).

    A plain ``LocalMemoryStore`` (a fully-local install with no engram leg at all)
    is the normal local backend, not a degraded one — it has no ``_engram``
    attribute, so it is never flagged degraded.
    """

    engram_owned = layer_value in _engram_layer_values()
    if not engram_owned:
        return "local", False
    if _store_has_live_engram(store):
        return "engram", False
    # Engram-owned layer with no live engram. Only a composite store (one that
    # *has* an engram leg) is "degraded"; a plain local store is simply local.
    is_composite = hasattr(store, "_engram")
    return "local", is_composite


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
        project_root: str | Path | None = None,
        allow_workflow_tools: bool = False,
    ) -> None:
        # When a runtime is provided, context/impact route through the verified
        # pipeline (gates/trust/trace). Without it, the legacy raw behavior is kept
        # for backward compatibility.
        self.runtime = runtime
        # Symbol-level write tools resolve the graph's relative file paths against
        # this root. Precedence: explicit argument, then the runtime's configured
        # project root, then the current working directory.
        self.project_root: Path = self._resolve_project_root(project_root, runtime)
        self.db = GraphDatabase(db_path=db_path)
        self.call_graph = CallGraphAnalyzer(db=self.db)
        self.impact = ImpactAnalyzer(db=self.db)
        self.context_builder = ContextBuilder(db_path=db_path)
        self.kg = KnowledgeGraph(db_path=db_path)
        # Permission gate: every tool call goes through ``policy.allows()``
        # before the handler runs. The safe default allowlists read + memory
        # tools only; ``allow_workflow_tools=True`` (the ``opencontext mcp
        # --workflow-tools`` opt-in every configured agent is registered with)
        # additionally unlocks ``opencontext_run`` and the session step tools —
        # NEVER the symbol-write tools. An explicit ``policy`` always wins.
        if policy is None:
            allowed = set(self._default_tool_names())
            if allow_workflow_tools:
                allowed.update(WORKFLOW_TOOL_NAMES)
            policy = ToolPermissionPolicy(allowed_tools=allowed)
        self.policy: ToolPermissionPolicy = policy
        # Raw stdin line buffer (see _next_line): we manage line splitting ourselves
        # so select() can't strand a buffered line on a batched write.
        self._inbuf: str = ""
        # Whether the connected client declared the MCP ``sampling`` capability at
        # initialize. Until initialize arrives, assume it cannot sample (safe: no
        # sampler is registered either way before initialize).
        self.client_supports_sampling: bool = False

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
                "description": (
                    "Get details about a specific symbol. Pass code=true to also return "
                    "its exact source (the KG knows the extent) — one call that replaces "
                    "'search to locate, then Read the file' for a targeted edit."
                ),
                "parameters": {
                    "symbol": {"type": "string", "description": "Symbol name"},
                    "file": {"type": "string", "description": "File path (optional)"},
                    "code": {
                        "type": "boolean",
                        "description": "Include the symbol's source code (default false).",
                        "default": False,
                    },
                },
            },
            "opencontext_files": {
                "description": "Get indexed file structure",
                "parameters": {
                    "filter": {"type": "string", "description": "Path filter (optional)"},
                    "max_depth": {"type": "integer", "default": 10},
                    "summarize": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return directory-level summaries (file count, symbol count) instead of individual files. Reduces token usage on large repos.",  # noqa: E501
                    },
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
            "opencontext_replace_symbol_body": {
                "description": "Replace a named symbol's definition span with new source text",
                "parameters": {
                    "symbol": {"type": "string", "description": "Symbol name to replace"},
                    "body": {"type": "string", "description": "Replacement source text"},
                    "file": {"type": "string", "description": "File path (optional)"},
                },
            },
            "opencontext_insert_before_symbol": {
                "description": "Insert source text immediately before a named symbol",
                "parameters": {
                    "symbol": {"type": "string", "description": "Symbol name to anchor on"},
                    "content": {"type": "string", "description": "Source text to insert"},
                    "file": {"type": "string", "description": "File path (optional)"},
                },
            },
            "opencontext_insert_after_symbol": {
                "description": "Insert source text immediately after a named symbol",
                "parameters": {
                    "symbol": {"type": "string", "description": "Symbol name to anchor on"},
                    "content": {"type": "string", "description": "Source text to insert"},
                    "file": {"type": "string", "description": "File path (optional)"},
                },
            },
            "opencontext_rename_symbol": {
                "description": "Rename a symbol at its definition and known call-graph references",
                "parameters": {
                    "symbol": {"type": "string", "description": "Current symbol name"},
                    "new_name": {"type": "string", "description": "New symbol name"},
                    "file": {"type": "string", "description": "File path (optional)"},
                },
            },
            "opencontext_run": {
                "description": (
                    "Drive the SDD agentic loop in-process using THIS host's selected "
                    "model via MCP sampling (zero provider config). Runs the workflow "
                    "phases (explore -> ... -> apply -> verify) and applies code edits."
                ),
                "parameters": {
                    "task": {"type": "string", "description": "Task / change to implement"},
                    "workflow": {
                        "type": "string",
                        "description": "Workflow track (sdd/standard/quick/...)",
                        "default": "sdd",
                    },
                    "root": {
                        "type": "string",
                        "description": (
                            "Project root to run in (defaults to the server's cwd). "
                            "Lets the SDD loop run on any indexed repo, not only the "
                            "one the server was started in."
                        ),
                    },
                },
            },
            "opencontext_memory_save": {
                "description": (
                    "Persist a memory record to OpenContext's own memory store. "
                    "Layer defaults to EPISODIC; use FAILURE for failures, SEMANTIC "
                    "for durable facts, PROCEDURAL for patterns."
                ),
                "parameters": {
                    "content": {"type": "string", "description": "The memory payload (required)"},
                    "layer": {
                        "type": "string",
                        "description": "Memory layer: episodic|semantic|procedural|working|failure (default episodic)",  # noqa: E501
                    },
                    "key": {"type": "string", "description": "Optional namespaced key"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional free-form tags",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Optional run id this memory came from (provenance)",
                    },
                    "provenance": {
                        "type": "string",
                        "description": "Optional origin: agent|harvest|manual|import",
                    },
                },
            },
            "opencontext_memory_search": {
                "description": "Search OpenContext's memory store for records matching a query",
                "parameters": {
                    "query": {"type": "string", "description": "Search query (required)"},
                    "scope": {
                        "type": "string",
                        "description": "Optional layer scope to restrict the search",
                    },
                    "limit": {"type": "integer", "default": 10},
                },
            },
            "opencontext_memory_context": {
                "description": (
                    "Return recent/relevant memory as markdown context for a task "
                    "(read-only; persists nothing)."
                ),
                "parameters": {
                    "query": {"type": "string", "description": "Task / query (required)"},
                },
            },
            "opencontext_memory_judge": {
                "description": (
                    "Curate an existing memory record by reinforcing or contradicting it "
                    "(the only curation verbs the store exposes)."
                ),
                "parameters": {
                    "memory_id": {"type": "string", "description": "ID of the record to curate"},
                    "relation": {
                        "type": "string",
                        "description": "Curation verb: 'reinforce' or 'contradict'",
                    },
                },
            },
            "opencontext_quality": {
                "description": (
                    "Evaluate architecture + code-quality on the changed scope (or whole "
                    "project); deterministic, zero model calls. The response also carries a "
                    "'trend' (latest/previous/delta/count) showing how the rolled-up health "
                    "score is moving across runs; a 'all'-scope scan advances the trend."
                ),
                "parameters": {
                    "scope": {
                        "type": "string",
                        "description": "'diff' (changed files) or 'all' (whole project)",
                        "default": "diff",
                    },
                    "rules": {
                        "type": "string",
                        "description": "Optional path to a quality.toml",
                        "default": None,
                    },
                },
            },
            # ── PR-013 session step tools (route through RuntimeApi) ──────────
            "opencontext_session_start": {
                "description": "Start a runtime session for a task (returns session_id).",
                "parameters": {
                    "task": {"type": "string", "description": "Task to start a session for"},
                    "profile": {"type": "string", "default": "balanced"},
                    "root": {"type": "string", "description": "Project root (optional)"},
                },
            },
            "opencontext_session_next": {
                "description": "Ask the runtime what the next action for a session is.",
                "parameters": {"session_id": {"type": "string"}},
            },
            "opencontext_session_observe": {
                "description": "Record an observation event on a session.",
                "parameters": {
                    "session_id": {"type": "string"},
                    "type": {"type": "string", "default": "note"},
                    "status": {"type": "string", "default": "ok"},
                    "message": {"type": "string"},
                },
            },
            "opencontext_session_apply": {
                "description": (
                    "Record a mutation on a session (governed). With kind='agent_edits' "
                    "it is the agent-execute follow-up: pass payload.changed_files "
                    "(files the agent edited itself) and OpenContext verifies them, "
                    "records receipts, and completes the linked run."
                ),
                "parameters": {
                    "session_id": {"type": "string"},
                    "kind": {"type": "string", "default": "edit"},
                    # NOTE: the nested properties MUST be declared. Strict hosts
                    # serialize an object parameter with no declared properties as
                    # {} (observed live: OpenCode + MiniMax sent payload={} on
                    # every call), which strands agent_execute follow-ups.
                    "payload": {
                        "type": "object",
                        "description": (
                            "Mutation payload. For kind='agent_edits': "
                            "{changed_files: [paths], oc_flow?: {session_id, run_id}, "
                            "test_command?: [argv]}"
                        ),
                        "properties": {
                            "changed_files": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": ("Relative paths of every file the agent edited"),
                            },
                            "oc_flow": {
                                "type": "object",
                                "description": (
                                    "Linked OC Flow run to complete (from the handoff)"
                                ),
                                "properties": {
                                    "session_id": {"type": "string"},
                                    "run_id": {"type": "string"},
                                },
                                "additionalProperties": True,
                            },
                            "test_command": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": ("Optional argv to run for verification evidence"),
                            },
                        },
                        "additionalProperties": True,
                    },
                    "root": {"type": "string", "description": "Project root (optional)"},
                },
            },
            "opencontext_session_inspect": {
                "description": "Inspect a session (runs/events/live state).",
                "parameters": {
                    "session_id": {"type": "string"},
                    "scope": {"type": "string", "default": "session"},
                },
            },
            "opencontext_session_status": {
                "description": "Return a session's current status.",
                "parameters": {"session_id": {"type": "string"}},
            },
            "opencontext_session_resume": {
                "description": "Resume a paused session from its last checkpoint.",
                "parameters": {"session_id": {"type": "string"}},
            },
            "opencontext_session_archive": {
                "description": "Archive a session (terminal).",
                "parameters": {"session_id": {"type": "string"}},
            },
            # ── PR-013 meta tools ────────────────────────────────────────────
            "opencontext_workflow_list": {
                "description": "List available workflows with cost and when-to-use.",
                "parameters": {"root": {"type": "string", "description": "Project root."}},
            },
            "opencontext_workflow_explain": {
                "description": "Explain a workflow: when/when-not/cost/phases/harnesses.",
                "parameters": {
                    "workflow": {"type": "string", "description": "Workflow id (e.g. sdd)"},
                    "root": {"type": "string"},
                },
            },
            "opencontext_profile_list": {
                "description": "List config profiles and per-phase model profiles.",
                "parameters": {},
            },
            "opencontext_profile_explain": {
                "description": "Explain a profile: security/budget/approvals/observability.",
                "parameters": {"profile": {"type": "string", "description": "Profile id"}},
            },
            "opencontext_doctor": {
                "description": "Validate configuration; return actionable findings.",
                "parameters": {"root": {"type": "string", "description": "Project root."}},
            },
        }

    def run(self) -> None:
        """Run the MCP server, reading from stdin and writing to stdout."""

        while True:
            message = self._read_message()
            if message is None:  # EOF
                break
            self._handle_request(message)

    def _next_line(self, timeout: float | None) -> str | None:
        """Return the next newline-terminated line from stdin (newline stripped),
        or None on EOF, or — when ``timeout`` is given — None if no line arrives
        before it.

        Reads raw bytes via the fd and splits lines into ``self._inbuf`` itself, so a
        host that batches several JSON-RPC messages into one write is never stranded
        by ``select`` (which reflects the kernel pipe, not Python's text buffer).
        Falls back to a blocking ``readline`` when stdin has no real fd (e.g. an
        in-memory test buffer).
        """
        while "\n" not in self._inbuf:
            try:
                fd = sys.stdin.fileno()
            except Exception:
                fd = None
            if fd is None:
                chunk = sys.stdin.readline()
                if not chunk:
                    break  # EOF
                self._inbuf += chunk
                continue
            if timeout is not None:
                try:
                    ready, _, _ = select.select([fd], [], [], timeout)
                except OSError:
                    # Windows: select() rejects non-socket fds (pipes/stdin) with
                    # WinError 10038. Fall back to a blocking read — the deadline is
                    # best-effort there; the host's sampling reply still arrives.
                    ready = [fd]
                if not ready:
                    return None
            raw = os.read(fd, 65536)
            if not raw:
                break  # EOF
            self._inbuf += raw.decode("utf-8", errors="replace")
        if "\n" in self._inbuf:
            line, _, self._inbuf = self._inbuf.partition("\n")
            return line
        if self._inbuf:  # trailing partial line at EOF
            line, self._inbuf = self._inbuf, ""
            return line
        return None

    def _read_message(self) -> dict[str, Any] | None:
        """Read one JSON-RPC message from stdin; None at EOF.

        Shared by the main loop and the sampling round-trip so server->client
        requests and incoming client messages read from one place.
        """
        while True:
            line = self._next_line(None)
            if line is None:
                return None
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                self._send_error(None, -32700, "Parse error")

    def _handle_request(self, request: dict[str, Any]) -> None:
        """Handle a single JSON-RPC request."""

        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        # Notifications (e.g. notifications/initialized) carry no id and MUST NOT
        # be answered — replying to one violates JSON-RPC.
        if method.startswith("notifications/"):
            return

        if method == "ping":
            self._send_response(request_id, {})
            return

        if method == "initialize":
            from opencontext_core.llm.sampling_gateway import register_host_sampler

            server_caps: dict[str, Any] = {"tools": {}}
            client_caps = params.get("capabilities", {})
            # Record the client's declared sampling capability. If the client can
            # sample, route the agentic loop's gateway through its selected model
            # (MCP sampling) — zero provider config needed. If it can NOT, clear
            # any stale sampler: sending sampling/createMessage to a client that
            # never answers would stall runs for the full sampling timeout.
            self.client_supports_sampling = (
                isinstance(client_caps, dict) and "sampling" in client_caps
            )
            if self.client_supports_sampling:
                register_host_sampler(self._request_sampling)
                server_caps["sampling"] = {}
            else:
                register_host_sampler(None)
            self._send_response(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": server_caps,
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
                    "outputSchema": _tool_output_schema(name),
                }
                for name, info in self.tools.items()
            ]
            self._send_response(request_id, {"tools": tools_list})
            return

        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_params = params.get("arguments", {})
            result = self._call_tool(tool_name, tool_params)
            self._send_response(request_id, _to_tool_result(result))
            return

        self._send_error(request_id, -32601, f"Method not found: {method}")

    def _call_tool(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call.

        Every tool call passes through :meth:`ToolPermissionPolicy.allows`
        before the handler runs. This is the single chokepoint for all MCP
        tools; the handler map below is only consulted if the policy allows
        the call.

        Returns a :class:`~opencontext_core.mcp.schemas.ToolResultEnvelope`
        dict for all outcomes. Success payload is under ``data``; denied/failed
        cases also include backward-compat ``error``/``reason`` keys so callers
        that check ``"error" in result`` still work.
        """

        from opencontext_core.mcp.schemas import (
            ToolPolicyDecision,
            ToolResultEnvelope,
            ToolWarning,
        )

        # 1. Policy gate. No tool executes without a prior policy check.
        if not self.policy.allows(name):
            d = ToolResultEnvelope(
                tool=name,
                status="denied",
                policy=ToolPolicyDecision(
                    decision="denied",
                    reason="tool_not_allowlisted",
                    policy="ToolPermissionPolicy",
                ),
            ).model_dump()
            # NOTE: backward compat — callers that check "error"/"reason" keys
            d["error"] = f"Tool '{name}' denied by policy"
            d["reason"] = "tool_not_allowlisted"
            return d

        handlers = self._handlers()
        handler = handlers.get(name)
        if handler is None:
            d = ToolResultEnvelope(
                tool=name,
                status="failed",
                warnings=[ToolWarning(code="unknown_tool", message=f"Unknown tool: {name}")],
            ).model_dump()
            d["error"] = f"Unknown tool: {name}"
            return d

        try:
            payload = cast("dict[str, Any]", handler(params))
            # Handlers that detect their own errors return {"error": ...} dicts.
            # Surface the error key so _to_tool_result sets isError=True.
            if "error" in payload:
                d = ToolResultEnvelope(
                    tool=name,
                    status="failed",
                    data=payload,
                ).model_dump()
                d["error"] = payload["error"]
                return d
            return ToolResultEnvelope(
                tool=name,
                status="passed",
                data=payload,
            ).model_dump()
        except Exception as exc:
            d = ToolResultEnvelope(
                tool=name,
                status="failed",
                warnings=[ToolWarning(code="exception", message=str(exc))],
            ).model_dump()
            d["error"] = str(exc)
            return d

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
            "opencontext_replace_symbol_body": self._handle_replace_symbol_body,
            "opencontext_insert_before_symbol": self._handle_insert_before_symbol,
            "opencontext_insert_after_symbol": self._handle_insert_after_symbol,
            "opencontext_rename_symbol": self._handle_rename_symbol,
            "opencontext_run": self._handle_run,
            "opencontext_memory_save": self._handle_memory_save,
            "opencontext_memory_search": self._handle_memory_search,
            "opencontext_memory_context": self._handle_memory_context,
            "opencontext_memory_judge": self._handle_memory_judge,
            "opencontext_quality": self._handle_quality,
            # PR-013 session step tools.
            "opencontext_session_start": self._handle_session_start,
            "opencontext_session_next": self._handle_session_next,
            "opencontext_session_observe": self._handle_session_observe,
            "opencontext_session_apply": self._handle_session_apply,
            "opencontext_session_inspect": self._handle_session_inspect,
            "opencontext_session_status": self._handle_session_status,
            "opencontext_session_resume": self._handle_session_resume,
            "opencontext_session_archive": self._handle_session_archive,
            # PR-013 meta tools.
            "opencontext_workflow_list": self._handle_workflow_list,
            "opencontext_workflow_explain": self._handle_workflow_explain,
            "opencontext_profile_list": self._handle_profile_list,
            "opencontext_profile_explain": self._handle_profile_explain,
            "opencontext_doctor": self._handle_doctor,
        }

    def _default_tool_names(self) -> list[str]:
        """Safe-by-default read-only + memory tool allowlist.

        Code-write tools (replace_symbol_body, insert_*, rename_symbol) and
        opencontext_run are NOT included here — they require an explicit
        policy opt-in so a vanilla server can't silently mutate source files.
        Pass ``policy=ToolPermissionPolicy(allowed_tools=set(server.tools.keys()))``
        to restore the full allowlist when needed (e.g. in write-tool tests).
        """

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
            "opencontext_memory_save",
            "opencontext_memory_search",
            "opencontext_memory_context",
            "opencontext_memory_judge",
            "opencontext_quality",
            # PR-013 read-only meta tools are safe by default. The session step
            # tools (start/next/observe/apply/resume/archive) write session state
            # and stay opt-in, like opencontext_run.
            "opencontext_session_inspect",
            "opencontext_session_status",
            "opencontext_workflow_list",
            "opencontext_workflow_explain",
            "opencontext_profile_list",
            "opencontext_profile_explain",
            "opencontext_doctor",
        ]

    def _handle_run(self, params: dict[str, Any]) -> dict[str, Any]:
        """Drive the agentic harness in-process through the shared Runtime API.

        Routes through ``runtime.api.RuntimeApi`` (the single boundary both the CLI
        and MCP share, SPEC-CLI-013-17) so the harness runs in THIS process, where
        the host sampler was registered during ``initialize`` (the standalone
        ``opencontext loop`` runs in a separate process where the sampler is
        absent). Returns the full :class:`RunContract` — ``session_id``/``summary``/
        ``artifacts{}``/``receipts{}``/``gates{}``/``cost{}``/``confidence{}``/
        ``next_recommended`` — never bare counts (SPEC-CLI-013-15).
        """
        from pathlib import Path

        from opencontext_core.llm.sampling_gateway import get_host_sampler
        from opencontext_core.runtime.api import (
            RunRequest,
            RuntimeApi,
            StartSessionRequest,
        )
        from opencontext_core.runtime.errors import RuntimeFailure
        from opencontext_core.runtime.run_contract import build_run_contract

        task = str(params.get("task", "")).strip()
        if not task:
            return {
                "error": "task is required",
                "code": "output_contract_failed",
                "next_action": "pass a non-empty 'task' argument",
                "recoverable": True,
            }
        workflow = str(params.get("workflow", "sdd")) or "sdd"
        profile = str(params.get("profile", "balanced")) or "balanced"
        root = Path(params.get("root") or Path.cwd()).resolve()

        from opencontext_core.mcp.run_dispatcher import dispatch_mcp_run

        dispatched = dispatch_mcp_run(
            task=task,
            workflow=workflow,
            root=root,
            profile=profile,
            lane=str(params.get("lane", "fast") or "fast"),
        )
        if dispatched is not None:
            return dispatched

        resolved = self._resolve_config(root)
        api = RuntimeApi(root=root, config=resolved.config)
        ref = api.start_session(StartSessionRequest(task=task, root=str(root), profile=profile))
        self._write_snapshot(resolved, ref.session_id, root)

        try:
            result = api.run(RunRequest(session_id=ref.session_id, workflow_id=workflow, task=task))
        except RuntimeFailure as exc:
            return {
                "error": exc.message,
                "code": str(exc.code),
                "next_action": exc.next_action,
                "recoverable": exc.recoverable,
                "session_id": ref.session_id,
                "run_id": "",
                "workflow": workflow,
                "status": "failed",
            }

        contract = build_run_contract(
            session_id=ref.session_id,
            run_id=result.run_id,
            workflow=workflow,
            status=result.status,
            legacy=result.legacy,
            host_model_used=get_host_sampler() is not None,
        )
        out = contract.model_dump()
        out.update(_sdd_run_metadata(result.legacy, workflow))
        if any(
            getattr(gate, "id", "") == "phase_contract"
            and str(getattr(getattr(gate, "status", None), "value", getattr(gate, "status", "")))
            == "failed"
            for gate in (getattr(result.legacy, "gates", []) or [])
        ):
            out["status"] = "blocked"

        # No sampler (client cannot sample) + no configured provider: the harness
        # just ran WITHOUT an executor, so a failed/blocked verdict is a dead end
        # the caller can never fix by retrying. Upgrade it to the agent-execute
        # handoff: the client agent does the work itself and completes this same
        # session via opencontext_session_apply (kind="agent_edits").
        from opencontext_core.mcp.agent_handoff import (
            build_workflow_agent_handoff,
            provider_is_mock,
        )

        if (
            out.get("status") in ("failed", "blocked", "scaffolded")
            and get_host_sampler() is None
            and provider_is_mock(resolved.config)
        ):
            out.update(
                build_workflow_agent_handoff(
                    root=root,
                    task=task,
                    workflow=workflow,
                    session_id=ref.session_id,
                    prior_status=str(out.get("status")),
                )
            )
        return out

    # ------------------------------------------------------------------ #
    # Runtime-API-backed session + meta tools (PR-013, SPEC-CLI-013-16). #
    # Each routes through the shared RuntimeApi facade and is governed by #
    # the same policy gate as every other tool (see ``_call_tool``).     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _best_effort_config(root: Path) -> Any:
        try:
            from opencontext_core.config import find_config, load_config

            path = find_config(root)
            return load_config(path) if path is not None else None
        except Exception:
            return None

    @staticmethod
    def _resolve_config(root: Path) -> Any:
        """Resolve the seven-layer config (always returns a config + provenance)."""
        from opencontext_core.config_resolver import resolve

        return resolve(root)

    @staticmethod
    def _write_snapshot(resolved: Any, session_id: str, root: Path) -> None:
        """Persist the per-session config snapshot (best-effort; never fails a run)."""
        try:
            from opencontext_core.config_snapshot import write_snapshot

            write_snapshot(
                resolved.config,
                session_id,
                root,
                provenance=getattr(resolved.provenance, "by_key", None),
            )
        except Exception:
            pass

    def _runtime_api(self, params: dict[str, Any]) -> RuntimeApi:
        from pathlib import Path

        from opencontext_core.runtime.api import RuntimeApi

        root = Path(params.get("root") or Path.cwd()).resolve()
        return RuntimeApi(root=root, config=self._best_effort_config(root))

    def _handle_session_start(self, params: dict[str, Any]) -> dict[str, Any]:
        from pathlib import Path

        from opencontext_core.runtime.api import RuntimeApi, StartSessionRequest

        task = str(params.get("task", "")).strip()
        if not task:
            return {"error": "task is required", "next_action": "pass a 'task'"}
        root = Path(params.get("root") or Path.cwd()).resolve()
        resolved = self._resolve_config(root)
        api = RuntimeApi(root=root, config=resolved.config)
        ref = api.start_session(
            StartSessionRequest(
                task=task,
                root=str(root),
                profile=str(params.get("profile", "balanced")),
            )
        )
        self._write_snapshot(resolved, ref.session_id, root)
        return ref.model_dump()

    def _handle_session_next(self, params: dict[str, Any]) -> dict[str, Any]:
        sid = str(params.get("session_id", "")).strip()
        if not sid:
            return {"error": "session_id is required"}
        return self._runtime_api(params).next(sid).model_dump()

    def _handle_session_observe(self, params: dict[str, Any]) -> dict[str, Any]:
        from opencontext_core.runtime.api import RuntimeEventInput

        sid = str(params.get("session_id", "")).strip()
        if not sid:
            return {"error": "session_id is required"}
        event = RuntimeEventInput(
            type=str(params.get("type", "note")),
            status=str(params.get("status", "ok")),
            message=str(params.get("message", "")),
            metadata=dict(params.get("metadata") or {}),
        )
        return self._runtime_api(params).observe(sid, event).model_dump()

    def _handle_session_apply(self, params: dict[str, Any]) -> dict[str, Any]:
        from opencontext_core.runtime.api import MutationRequest

        sid = str(params.get("session_id", "")).strip()
        if not sid:
            return {"error": "session_id is required"}
        mutation = MutationRequest(
            kind=str(params.get("kind", "edit")), payload=dict(params.get("payload") or {})
        )
        return self._runtime_api(params).apply(sid, mutation).model_dump()

    def _handle_session_inspect(self, params: dict[str, Any]) -> dict[str, Any]:
        from opencontext_core.runtime.api import InspectionScope

        sid = str(params.get("session_id", "")).strip()
        if not sid:
            return {"error": "session_id is required"}
        scope_raw = str(params.get("scope", "session"))
        try:
            scope = InspectionScope(scope_raw)
        except ValueError:
            scope = InspectionScope.session
        return self._runtime_api(params).inspect(sid, scope).model_dump()

    def _handle_session_status(self, params: dict[str, Any]) -> dict[str, Any]:
        sid = str(params.get("session_id", "")).strip()
        if not sid:
            return {"error": "session_id is required"}
        from opencontext_core.runtime.api import InspectionScope

        return self._runtime_api(params).inspect(sid, InspectionScope.session).model_dump()

    def _handle_session_resume(self, params: dict[str, Any]) -> dict[str, Any]:
        sid = str(params.get("session_id", "")).strip()
        if not sid:
            return {"error": "session_id is required"}
        return self._runtime_api(params).resume(sid).model_dump()

    def _handle_session_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        sid = str(params.get("session_id", "")).strip()
        if not sid:
            return {"error": "session_id is required"}
        return self._runtime_api(params).archive(sid).model_dump()

    def _handle_workflow_list(self, params: dict[str, Any]) -> dict[str, Any]:
        from opencontext_core.explain import list_workflows

        root = params.get("root") or "."
        return {"workflows": list_workflows(root)}

    def _handle_workflow_explain(self, params: dict[str, Any]) -> dict[str, Any]:
        from opencontext_core.explain import explain_workflow

        workflow_id = str(params.get("workflow", "")).strip()
        if not workflow_id:
            return {"error": "workflow is required"}
        return explain_workflow(workflow_id, params.get("root") or ".")

    def _handle_profile_list(self, params: dict[str, Any]) -> dict[str, Any]:
        from opencontext_core.explain import list_profiles_all

        return list_profiles_all()

    def _handle_profile_explain(self, params: dict[str, Any]) -> dict[str, Any]:
        from opencontext_core.explain import explain_profile

        profile_id = str(params.get("profile", "")).strip()
        if not profile_id:
            return {"error": "profile is required"}
        return explain_profile(profile_id)

    def _handle_doctor(self, params: dict[str, Any]) -> dict[str, Any]:
        from opencontext_core.config_doctor import validate

        root = params.get("root") or "."
        diags = validate(root)
        findings = [
            {
                "name": d.name,
                "status": d.status,
                "message": d.message,
                "recommendation": d.recommendation,
            }
            for d in diags
        ]
        failed = sum(1 for d in diags if d.status in ("failed", "error"))
        return {"ok": failed == 0, "failed": failed, "findings": findings}

    # ----------------------------------------------------------------------- #
    # Memory tools (workstream A). All four degrade cleanly when no store is
    # wired (structured error, never raise), mirroring the runtime-optional
    # guard the read tools use. The store is OpenContext's own
    # ``CompositeMemoryStore`` (routing to Engram is automatic).
    # ----------------------------------------------------------------------- #

    def _memory_store(self) -> Any | None:
        """Resolve the live memory store, or None when unavailable.

        Mirrors the runtime-optional guard elsewhere in this server: only reads
        ``_v2_memory_store`` when a runtime is actually attached. Returns None so
        every memory handler can emit a structured error instead of raising
        (A-REQ-4a).
        """

        runtime = getattr(self, "runtime", None)
        if runtime is None:
            return None
        return getattr(runtime, "_v2_memory_store", None)

    def _memory_status(self) -> dict[str, Any]:
        """Snapshot of the live memory backend for the ``opencontext_status`` probe.

        Mirrors PR-AHE-007 task 7.3 — agents can detect availability from the
        status tool without first issuing a save and getting an error. The shape
        is small and additive so existing callers keep working.

        Returns a dict with at minimum ``available`` (bool), ``backend`` (one
        of ``local``/``composite``), and ``reason`` (actionable text when
        ``available`` is False; empty when it is True).
        """

        store = self._memory_store()
        if store is None:
            return {
                "available": False,
                "backend": "none",
                "reason": _MEMORY_UNAVAILABLE_REASON,
            }
        if _is_composite_store(store):
            return {
                "available": True,
                "backend": "composite",
                "engram_layers": sorted(_engram_layer_values()),
                "local_layers": sorted(_local_layer_values()),
                "live_engram": _store_has_live_engram(store),
                "reason": "",
            }
        # Plain LocalMemoryStore (no engram leg at all).
        return {
            "available": True,
            "backend": "local",
            "reason": "",
        }

    @staticmethod
    def _serialize_record(record: Any) -> dict[str, Any]:
        """Project a ``MemoryRecord`` to a JSON-safe result dict."""

        layer = getattr(record, "layer", None)
        result: dict[str, Any] = {
            "id": getattr(record, "id", None),
            "layer": getattr(layer, "value", layer),
            "key": getattr(record, "key", None),
            "content": getattr(record, "content", None),
            "confidence": getattr(record, "confidence", None),
            "tags": list(getattr(record, "tags", []) or []),
        }
        run_id = getattr(record, "run_id", None)
        provenance = getattr(record, "provenance", None)
        if run_id is not None:
            result["run_id"] = run_id
        if provenance is not None:
            result["provenance"] = provenance
        return result

    def _handle_memory_save(self, params: dict[str, Any]) -> dict[str, Any]:
        """Persist a memory record to the live store (A-REQ-2/3/4)."""

        store = self._memory_store()
        if store is None:
            return _memory_unavailable_envelope()

        try:
            record = _make_memory_record(params)
        except ValueError as exc:
            # Invalid layer (or other validation) -> structured error, no write.
            return {"error": str(exc)}

        record_id = store.write(record)
        backend, degraded = _resolve_backend(store, record.layer.value)
        result: dict[str, Any] = {
            "id": record_id or record.id,
            "layer": record.layer.value,
            "key": record.key,
            "backend": backend,
            "degraded": degraded,
        }
        # Echo provenance only when supplied — keeps the response shape stable.
        if record.run_id is not None:
            result["run_id"] = record.run_id
        if record.provenance is not None:
            result["provenance"] = record.provenance
        return result

    def _handle_memory_search(self, params: dict[str, Any]) -> dict[str, Any]:
        """Search the memory store, optionally scoped to a layer (A-REQ-5)."""

        store = self._memory_store()
        if store is None:
            return _memory_unavailable_envelope()

        from opencontext_core.models.agent_memory import MemoryLayer

        query = str(params.get("query", ""))
        scope_value = params.get("scope")
        scope: MemoryLayer | None = None
        if scope_value:
            try:
                scope = MemoryLayer(scope_value)
            except ValueError:
                allowed = ", ".join(m.value for m in MemoryLayer)
                return {"error": f"invalid scope {scope_value!r}; allowed layers: {allowed}"}
        limit = params.get("limit") or 10

        records = store.search(query, scope=scope, limit=limit)
        return {"results": [self._serialize_record(r) for r in records]}

    def _handle_memory_context(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return recent/relevant memory as markdown context (read-only, A-REQ-5)."""

        store = self._memory_store()
        if store is None:
            return _memory_unavailable_envelope()

        query = str(params.get("query", ""))
        records = store.search(query, scope=None, limit=10)
        lines = [
            f"- [{self._serialize_record(r)['layer']}] {getattr(r, 'content', '')}" for r in records
        ]
        context = "\n".join(lines)
        return {"context": context, "count": len(records)}

    def _handle_memory_judge(self, params: dict[str, Any]) -> dict[str, Any]:
        """Curate one record via reinforce/contradict — the only verbs the store
        exposes (A-REQ-5 / N2). Any other relation is a structured error."""

        store = self._memory_store()
        if store is None:
            return _memory_unavailable_envelope()

        memory_id = str(params.get("memory_id", ""))
        relation = str(params.get("relation", ""))
        if relation not in _JUDGE_RELATIONS:
            allowed = ", ".join(_JUDGE_RELATIONS)
            return {
                "error": f"invalid relation {relation!r}; allowed relations: {allowed}",
            }
        if not memory_id:
            return {"error": "memory_id is required"}

        from opencontext_core.models.evidence import EvidenceRef

        # Synthesize a minimal self-referential evidence ref when none is supplied:
        # the judgment itself is the evidence (design N2).
        evidence = EvidenceRef(
            source=f"judge:{memory_id}",
            source_type="memory",
            confidence=1.0,
            verified=False,
        )
        if relation == "reinforce":
            store.reinforce(memory_id, evidence)
        else:
            store.contradict(memory_id, evidence)
        return {"id": memory_id, "relation": relation, "ok": True}

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

    def _project_profile_block(self) -> str:
        """Durable project DOMAIN context as a markdown block (cached, best-effort).

        Reads ``<root>/opencontext.yaml`` once and renders ``project.profile``
        (purpose/audience/problem/key_decisions) — the product context the
        knowledge graph cannot derive from code. Returns "" when there is no
        profile or the config can't be read, so it never breaks context building.
        """
        cached = getattr(self, "_profile_block_cache", None)
        if cached is not None:
            return cast("str", cached)

        block = ""
        try:
            import yaml

            from opencontext_core.config import ProjectProfile

            cfg_path = self.project_root / "opencontext.yaml"
            if cfg_path.is_file():
                raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                profile_data = (raw.get("project") or {}).get("profile")
                if isinstance(profile_data, dict):
                    block = ProjectProfile.model_validate(profile_data).to_context_block()
        except Exception:
            block = ""  # best-effort: a missing/invalid profile never blocks context
        self._profile_block_cache = block
        return block

    def _handle_context(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle context building tool."""

        task = params.get("task", "")
        # Route through the verified pipeline when a runtime is wired (surface parity).
        if self.runtime is not None:
            return self._verified_context(task)

        max_nodes = params.get("max_nodes")
        format = params.get("format", "markdown")

        # Adaptive scaling only when the caller OMITS max_nodes — an explicit value
        # (even 20) is honored, not overridden by the stats-derived default.
        if max_nodes is None:
            try:
                stats = self.db.get_stats()
                max_nodes = _compute_max_nodes(stats.get("files", 0))
            except Exception:
                max_nodes = _MAX_NODES_FALLBACK

        context = self.context_builder.build_context(
            task=task,
            max_nodes=max_nodes,
            format=format,
        )
        rendered = self.context_builder.render(context)

        # Ground the task in the project's DURABLE domain context (purpose/audience/
        # problem/decisions) — what the code graph can't tell the agent. Prepended
        # so it leads the pack; omitted entirely when no profile is authored.
        profile_block = self._project_profile_block()
        if profile_block:
            rendered = f"{profile_block}\n\n{rendered}" if rendered else profile_block

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
            # Single source of truth: the analyzer derives risk from the full
            # blast radius (callers, dependents, files, tests, centrality).
            "risk_level": impact.risk_level,
            "centrality": impact.centrality,
        }

    def _handle_node(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle node details tool."""

        symbol = params.get("symbol", "")
        file = params.get("file")
        include_code = bool(params.get("code", False))

        node_id = self._find_node(symbol, file)
        if node_id is None:
            return {"error": f"Symbol not found: {symbol}"}

        node = self.db.get_node_by_id(node_id)
        if node is None:
            return {"error": f"Node not found: {node_id}"}

        from opencontext_core.indexing.scip_symbol import format_symbol

        result = {
            "name": node.name,
            "kind": node.kind,
            # Structured, decodable identity (language/package/file/type/role).
            "symbol": format_symbol(
                language=node.language,
                file_path=node.file_path,
                name=node.name,
                kind=node.kind,
                container=node.container,
            ),
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
        # One-call surgical edit support: the KG already knows the symbol's exact extent
        # (line..end_line), so return JUST its source — a single call that replaces
        # "search to locate, then Read the whole file region". On a large file this is
        # far fewer tokens than reading around the hit.
        if include_code and node.line and node.end_line:
            try:
                src = (self.project_root / node.file_path).read_text(
                    encoding="utf-8", errors="ignore"
                )
                result["code"] = "\n".join(src.splitlines()[node.line - 1 : node.end_line])
            except OSError:
                pass
        return result

    def _handle_files(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle file structure tool."""

        filter_pattern = params.get("filter")
        max_depth = params.get("max_depth", 10)
        summarize = params.get("summarize", False)

        conn = self.db._connect()
        if filter_pattern:
            rows = conn.execute(
                "SELECT path, language FROM files WHERE path LIKE ? ORDER BY path LIMIT ?",
                (f"%{filter_pattern}%", 1000),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT path, language FROM files ORDER BY path LIMIT ?",
                (1000,),
            ).fetchall()

        if summarize:
            dirs: dict[str, dict[str, Any]] = {}
            for row in rows:
                path = row[0]
                parts = Path(path).parts
                if len(parts) > max_depth:
                    continue
                dir_key = str(Path(path).parent) if len(parts) > 1 else "."
                if dir_key not in dirs:
                    dirs[dir_key] = {"dir": dir_key, "files": 0, "symbols": 0, "languages": set()}
                dirs[dir_key]["files"] += 1
                dirs[dir_key]["languages"].add(row[1] or "unknown")
            # Enrich with symbol counts
            sym_rows = conn.execute(
                "SELECT file_path, COUNT(*) as cnt FROM nodes GROUP BY file_path"
            ).fetchall()
            for sym_row in sym_rows:
                dir_key = str(Path(sym_row[0]).parent) if len(Path(sym_row[0]).parts) > 1 else "."
                if dir_key in dirs:
                    dirs[dir_key]["symbols"] += sym_row[1]
            result = [
                {
                    **{k: v for k, v in d.items() if k != "languages"},
                    "languages": sorted(d["languages"]),
                }
                for d in dirs.values()
            ]
            return {"directories": sorted(result, key=lambda x: x["dir"])}

        files = []
        for row in rows:
            path = row[0]
            depth = len(Path(path).parts)
            if depth <= max_depth:
                files.append({"path": path, "language": row[1]})

        return {"files": files}

    def _handle_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle status tool.

        Returns the live KG snapshot plus a ``memory`` section so an agent can
        detect memory availability without first issuing a save (PR-AHE-007
        task 7.3). The memory section is keyed off the same ``_v2_memory_store``
        the memory handlers reach, so it always reflects the live wiring.
        """

        stats = self.db.get_stats()
        return {
            "indexed": stats.get("nodes", 0) > 0,
            "nodes": stats.get("nodes", 0),
            "edges": stats.get("edges", 0),
            "files": stats.get("files", 0),
            "memory": self._memory_status(),
        }

    def _handle_quality(self, params: dict[str, Any]) -> dict[str, Any]:
        """Evaluate architecture + code-quality and return a report dict.

        Runs the SAME deterministic :class:`QualityEvaluator` the harness gate
        and the CLI use — graph analysis plus the configured language-tool
        subprocesses, and **never** the model — so the check path stays exactly
        token-free. ``scope='diff'`` (the default) evaluates the working-tree
        changed files; ``scope='all'`` evaluates the whole project. The optional
        ``rules`` path overrides the project's ``quality.toml``.

        Returns the evaluator's ``QualityReport.to_report_dict()`` (JSON-safe
        primitives: ``summary``/``results``/``health``/``delta``). Any failure
        degrades to a structured ``{'error': ...}`` (the memory-handler pattern);
        ``_to_tool_result`` auto-wraps, redacts, and sets ``isError``. All imports
        are local so importing this server never pulls the quality package (which
        imports ``harness.models``) — keeping the harness<->quality edge lazy.
        """

        from opencontext_core.harness.runner import HarnessRunner
        from opencontext_core.quality.evaluator import QualityEvaluator
        from opencontext_core.quality.rules import (
            QualityConfigError,
            QualityRules,
            load_rules,
            parse_rules,
        )

        scope = str(params.get("scope") or "diff").strip().lower()
        if scope not in ("diff", "all"):
            return {"error": f"invalid scope {scope!r}; expected 'diff' or 'all'"}

        # Resolve the project root the same way the write tools do (explicit root,
        # then runtime config, then cwd) — this is also where the KG DB and the
        # quality.toml live.
        root = self.project_root

        # Resolve rules: an explicit ``rules`` path is parsed directly; otherwise
        # the project's quality.toml is loaded (zero-config falls back to defaults).
        import tomllib

        rules: QualityRules | None
        rules_path = params.get("rules")
        try:
            if rules_path:
                config_path = Path(rules_path)
                if not config_path.exists():
                    return {"error": f"rules file not found: {rules_path}"}
                rules = parse_rules(tomllib.loads(config_path.read_text(encoding="utf-8")))
            else:
                rules = load_rules(root)
        except (QualityConfigError, tomllib.TOMLDecodeError, OSError, ValueError) as exc:
            return {"error": f"invalid quality rules: {exc}"}

        try:
            evaluator = QualityEvaluator(root, rules=rules)
            if scope == "diff":
                changed_files = HarnessRunner._git_changed_files(root)
            else:
                # Whole project: the scanned-source relative paths are the full
                # file set (so both the architecture scope filter and the language
                # tools see the whole repo). Deterministic and self-contained.
                changed_files = [s.relative_path for s in evaluator._scanned()]
            report = evaluator.evaluate(changed_files)
            result = report.to_report_dict()
            # Surface the cross-run evolution trend so an agent can see how the
            # rolled-up health score is MOVING, not just this run's snapshot. This
            # is READ-ONLY by design: the tool never writes (the CLI `quality
            # check` and the harness are the recorders), so the check path stays
            # side-effect-free and byte-deterministic. Missing log -> count 0.
            try:
                from opencontext_core.quality.evolution import (
                    EVOLUTION_FILENAME,
                    EvolutionStore,
                )

                trend = EvolutionStore(root / EVOLUTION_FILENAME).trend()
                result["trend"] = {
                    "latest": trend.latest,
                    "previous": trend.previous,
                    "delta": trend.delta,
                    "count": trend.count,
                }
            except Exception:
                result["trend"] = None  # best-effort; never fail the check
            return result
        except Exception as exc:
            return {"error": str(exc)}

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

    # ---- Symbol-level write tools ----
    #
    # These resolve a named symbol to its graph span (file + 1-based line range)
    # and apply a precise, atomic edit to the source file. Resolution failures
    # return a clean error dict (never an exception) and never touch the file.

    def _write_approval_required(self) -> bool:
        """Whether disk-writing symbol-edit tools must pass the approval gate.

        Reads ``runtime.config.tools.mcp.require_write_approval`` defensively;
        defaults to ``False`` when no runtime/config is attached so a vanilla
        server (and every existing caller) keeps today's behavior exactly
        (C2-1a / RD4). Mirrors the runtime-optional guard used by the read and
        memory tools.
        """

        runtime = getattr(self, "runtime", None)
        if runtime is None:
            return False
        try:
            return bool(runtime.config.tools.mcp.require_write_approval)
        except Exception:
            return False

    def _write_approval_denied(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """Evaluate the write-approval gate before any disk write.

        Returns a structured "approval required" denial dict when the gate FAILS
        (approval required by config but not granted via ``approved=true`` in the
        call params), so the caller writes nothing. Returns ``None`` when the
        write may proceed (approval not required, or granted). Reuses the
        harness ``ApprovalRequiredForWritesGate`` unchanged (decision RD4).
        """

        approval_required = self._write_approval_required()
        if not approval_required:
            return None
        from opencontext_core.harness.gates import ApprovalRequiredForWritesGate
        from opencontext_core.harness.models import GateStatus

        approved = bool(params.get("approved", False))
        gate = ApprovalRequiredForWritesGate().evaluate(approval_required, approved)
        if gate.status is GateStatus.FAILED:
            return {
                "error": gate.message,
                "approval_required": True,
                "applied": False,
                "hint": "re-issue the call with approved=true once a human has approved the write",
            }
        return None

    def _handle_replace_symbol_body(self, params: dict[str, Any]) -> dict[str, Any]:
        """Replace a symbol's definition span with new source text."""

        denied = self._write_approval_denied(params)
        if denied is not None:
            return denied

        symbol = params.get("symbol", "")
        file = params.get("file")
        body = params.get("body")
        if body is None:
            return {"error": "Missing 'body'", "applied": False}

        node = self._resolve_symbol(symbol, file)
        if node is None:
            return {
                "error": f"Symbol not found: {symbol}",
                "applied": False,
                "hint": (
                    "These symbol-write tools edit only THIS session's indexed project. "
                    "To change a different repo, use the native Edit tool on the source "
                    "from `opencontext_node` (code=true), or index that project first."
                ),
            }

        try:
            lines, trailing = self._read_file_lines(node.file_path)
        except OSError as exc:
            return {"error": f"Cannot read file: {exc}", "applied": False, "symbol": symbol}

        start = node.line - 1  # graph lines are 1-based
        end = node.end_line  # exclusive slice bound (end_line is inclusive 1-based)
        if start < 0 or end > len(lines) or start >= end:
            return {
                "error": f"Symbol span out of range for {symbol}",
                "applied": False,
                "symbol": symbol,
            }

        replacement = _split_lines(body)[0]
        new_lines = lines[:start] + replacement + lines[end:]
        syntax_err = _python_syntax_error(node.file_path, _join_lines(new_lines, trailing))
        if syntax_err:
            return {
                "error": syntax_err,
                "applied": False,
                "symbol": symbol,
                "hint": "pass the full definition (signature + body), not just the body",
            }
        applied = self._write_file_lines(node.file_path, new_lines, trailing)
        return {
            "tool": "opencontext_replace_symbol_body",
            "file": node.file_path,
            "symbol": symbol,
            "applied": applied,
            "changed_range": {"start_line": node.line, "end_line": node.end_line},
        }

    def _handle_insert_before_symbol(self, params: dict[str, Any]) -> dict[str, Any]:
        """Insert source text immediately before a symbol's definition."""

        return self._insert_relative_to_symbol(params, after=False)

    def _handle_insert_after_symbol(self, params: dict[str, Any]) -> dict[str, Any]:
        """Insert source text immediately after a symbol's definition."""

        return self._insert_relative_to_symbol(params, after=True)

    def _insert_relative_to_symbol(self, params: dict[str, Any], *, after: bool) -> dict[str, Any]:
        """Shared insert logic for the before/after variants."""

        denied = self._write_approval_denied(params)
        if denied is not None:
            return denied

        symbol = params.get("symbol", "")
        file = params.get("file")
        content = params.get("content")
        tool = "opencontext_insert_after_symbol" if after else "opencontext_insert_before_symbol"
        if content is None:
            return {"error": "Missing 'content'", "applied": False}

        node = self._resolve_symbol(symbol, file)
        if node is None:
            return {
                "error": f"Symbol not found: {symbol}",
                "applied": False,
                "hint": (
                    "These symbol-write tools edit only THIS session's indexed project. "
                    "To change a different repo, use the native Edit tool on the source "
                    "from `opencontext_node` (code=true), or index that project first."
                ),
            }

        try:
            lines, trailing = self._read_file_lines(node.file_path)
        except OSError as exc:
            return {"error": f"Cannot read file: {exc}", "applied": False, "symbol": symbol}

        insert_at = node.end_line if after else node.line - 1
        insert_at = max(0, min(insert_at, len(lines)))
        block = _split_lines(content)[0]
        new_lines = lines[:insert_at] + block + lines[insert_at:]
        syntax_err = _python_syntax_error(node.file_path, _join_lines(new_lines, trailing))
        if syntax_err:
            return {"error": syntax_err, "applied": False, "symbol": symbol}
        applied = self._write_file_lines(node.file_path, new_lines, trailing)
        return {
            "tool": tool,
            "file": node.file_path,
            "symbol": symbol,
            "applied": applied,
            "changed_range": {
                "start_line": insert_at + 1,
                "end_line": insert_at + len(block),
            },
        }

    def _handle_rename_symbol(self, params: dict[str, Any]) -> dict[str, Any]:
        """Rename a symbol at its definition and known call-graph references.

        References come from the call graph: each ``calls`` edge targeting the
        symbol records the file + line of a call site. We rewrite the identifier
        (whole-word) on the definition line and on every recorded call-site line.
        The ``updated`` field lists exactly which lines changed. Edges are stored
        one-per caller/callee pair, so a caller that references the symbol on
        several lines records only one of them; callers should consult
        ``updated`` and re-index if a file has repeated references.
        """

        denied = self._write_approval_denied(params)
        if denied is not None:
            return denied

        symbol = params.get("symbol", "")
        file = params.get("file")
        new_name = params.get("new_name")
        if not new_name:
            return {"error": "Missing 'new_name'", "applied": False}
        if not new_name.isidentifier():
            return {"error": f"Invalid identifier: {new_name}", "applied": False}
        import keyword

        if keyword.iskeyword(new_name) or keyword.issoftkeyword(new_name):
            return {"error": f"'{new_name}' is a Python keyword", "applied": False}

        node = self._resolve_symbol(symbol, file)
        if node is None or node.id is None:
            return {
                "error": f"Symbol not found: {symbol}",
                "applied": False,
                "hint": (
                    "These symbol-write tools edit only THIS session's indexed project. "
                    "To change a different repo, use the native Edit tool on the source "
                    "from `opencontext_node` (code=true), or index that project first."
                ),
            }

        # Collect rename targets: start with the definition line, then add each call site.
        targets: dict[str, set[int]] = {node.file_path: {node.line}}
        for site_file, site_line in self._reference_sites(node.id):
            targets.setdefault(site_file, set()).add(site_line)

        updated: list[dict[str, Any]] = []
        files_touched = 0
        for rel_path, line_numbers in targets.items():
            try:
                lines, trailing = self._read_file_lines(rel_path)
            except OSError:
                continue
            file_hits = 0
            rewritten_idxs: set[int] = set()
            for line_no in line_numbers:
                idx = line_no - 1
                if 0 <= idx < len(lines):
                    rewritten, hits = _replace_identifier(lines[idx], symbol, new_name)
                    if hits:
                        lines[idx] = rewritten
                        file_hits += hits
                        rewritten_idxs.add(idx)
                        updated.append({"file": rel_path, "line": line_no, "occurrences": hits})
            # Also fix `from m import <symbol>` lines in this file: a rename that
            # touches the call sites but not the import leaves a dangling import that
            # no longer resolves. Restricted to import lines so unrelated same-named
            # tokens elsewhere are not rewritten.
            for idx, line in enumerate(lines):
                if idx in rewritten_idxs or not _IMPORT_LINE_RE.match(line):
                    continue
                rewritten, hits = _replace_identifier(line, symbol, new_name)
                if hits:
                    lines[idx] = rewritten
                    file_hits += hits
                    updated.append({"file": rel_path, "line": idx + 1, "occurrences": hits})
            if file_hits and self._write_file_lines(rel_path, lines, trailing):
                files_touched += 1

        return {
            "tool": "opencontext_rename_symbol",
            "file": node.file_path,
            "symbol": symbol,
            "new_name": new_name,
            "applied": bool(updated),
            "updated": updated,
            "files_changed": files_touched,
        }

    def _reference_sites(self, node_id: str) -> list[tuple[str, int]]:
        """Return (file, line) call sites that reference ``node_id`` from the graph."""

        conn = self.db._connect()
        rows = conn.execute(
            """
            SELECT call_site_file, call_site_line
            FROM edges
            WHERE target_node_id = ? AND kind = 'calls'
              AND call_site_file IS NOT NULL AND call_site_line IS NOT NULL
            """,
            (node_id,),
        ).fetchall()
        return [(row["call_site_file"], row["call_site_line"]) for row in rows]

    def _resolve_symbol(self, symbol: str, file: str | None = None) -> Node | None:
        """Resolve a symbol name to its full graph node (with line span)."""

        node_id = self._find_node(symbol, file)
        if node_id is None:
            return None
        return self.db.get_node_by_id(node_id)

    def _abs_path(self, rel_path: str) -> Path:
        """Map a graph-relative file path to an absolute path under the root.

        Absolute paths stored in the graph are returned unchanged.
        """

        candidate = Path(rel_path)
        if candidate.is_absolute():
            return candidate
        return (self.project_root / candidate).resolve()

    def _read_file_lines(self, rel_path: str) -> tuple[list[str], bool]:
        """Read a source file as lines plus a trailing-newline flag."""

        text = self._abs_path(rel_path).read_text(encoding="utf-8")
        return _split_lines(text)

    def _write_file_lines(self, rel_path: str, lines: list[str], trailing: bool) -> bool:
        """Atomically write lines back to a source file (temp + replace)."""

        return write_text_atomic(self._abs_path(rel_path), _join_lines(lines, trailing))

    @staticmethod
    def _resolve_project_root(
        project_root: str | Path | None,
        runtime: OpenContextRuntime | None,
    ) -> Path:
        """Pick the root for resolving relative graph paths in write tools."""

        if project_root is not None:
            return Path(project_root).resolve()
        if runtime is not None:
            try:
                return Path(runtime.config.project_index.root).resolve()
            except Exception:
                pass
        return Path.cwd()

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

    def _send_request(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        """Send a server->client JSON-RPC request (e.g. sampling/createMessage)."""

        self._write_json({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})

    def _request_sampling(
        self,
        system_prompt: str,
        prompt: str,
        max_tokens: int,
        model: str | None = None,
        *,
        timeout: float = 60.0,
    ) -> str:
        """Host sampler: run a generation on the client's selected model via MCP
        sampling. Sends ``sampling/createMessage`` and waits for the matching
        response, handling any client requests that interleave the round-trip.

        Bounded by ``timeout``: a host that advertises ``sampling`` but never
        answers would otherwise deadlock the server forever on ``readline()``.
        Returns ``""`` on timeout, disconnect, or an error response.
        """
        from opencontext_core.safety.secrets import SecretScanner

        self._sampling_seq = getattr(self, "_sampling_seq", 0) + 1
        req_id = f"oc-sampling-{self._sampling_seq}"
        # Scrub secrets from the prompt before it reaches the host's model.
        scanner = SecretScanner()
        params: dict[str, Any] = {
            "messages": [
                {"role": "user", "content": {"type": "text", "text": scanner.redact(prompt)}}
            ],
            "maxTokens": max_tokens,
        }
        if system_prompt:
            params["systemPrompt"] = scanner.redact(system_prompt)
        # Per-role/per-phase model → MCP modelPreferences hint, so the client picks
        # the matching model (opus/sonnet/haiku, codex 5.4-mini/5.5, …) for this unit
        # of work. A placeholder ("mock"/"host-selected") means "use whatever model
        # the user already selected in their agent" — we send no hint.
        if model and model not in ("host-selected", "mock", "mock-llm"):
            params["modelPreferences"] = {"hints": [{"name": model}]}
        self._send_request(req_id, "sampling/createMessage", params)
        deadline = time.monotonic() + timeout
        while True:
            msg = self._read_message_before(deadline)
            if msg is None:
                return ""  # timed out or client disconnected mid-request
            if msg.get("id") == req_id:
                if "error" in msg:
                    return ""  # client refused/failed the sampling request
                content = (msg.get("result") or {}).get("content", {})
                return str(content.get("text", "")) if isinstance(content, dict) else str(content)
            if "method" in msg:  # interleaved client request — service it
                self._handle_request(msg)

    def _read_message_before(self, deadline: float) -> dict[str, Any] | None:
        """Read one JSON-RPC message, or None if ``deadline`` passes first.

        Goes through ``_next_line`` (shared buffer) so a silent host cannot block
        forever AND a host that batches messages into one write is not stranded.
        """
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            line = self._next_line(remaining)
            if line is None:
                return None  # EOF or timed out
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                self._send_error(None, -32700, "Parse error")

    @staticmethod
    def _write_json(data: dict[str, Any]) -> None:
        """Write JSON data to stdout with flush."""

        sys.stdout.write(json.dumps(data) + "\n")
        sys.stdout.flush()

    def close(self) -> None:
        """Close all resources."""

        self.db.close()
        self.context_builder.close()
