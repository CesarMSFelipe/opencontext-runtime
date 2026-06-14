# Current Retrieval Paths

Status: implementation audit for unified graph-aware retrieval  
Updated: June 12, 2026

## Runtime context packs

`OpenContextRuntime._build_context_pack_with_trace()` is the local context-pack
path used by `build_context_pack()` and adapter preparation. It now generates
candidates through `RetrievalPlanner`, then keeps the existing ranking, packing,
sanitization, firewall, and trace steps unchanged.

```text
Runtime request
  -> RetrievalPlanner
      -> ManifestRetrievalSource(ProjectRetriever)
      -> GraphRetrievalSource(ContextBuilder, optional)
  -> ContextRanker
  -> ContextPackBuilder
  -> sanitize_context_pack
  -> ContextFirewall
  -> LocalTraceLogger
```

## Manifest retrieval

`ProjectRetriever` remains the baseline source. It reads the project manifest and
working tree, emits `ContextItem` candidates for matched files and symbols, and
keeps its fallback to the first manifest files when no query match exists.

## Native graph context

`ContextBuilder` remains the native graph source for symbol search and shallow
relationship expansion over the SQLite knowledge graph. The planner treats it as
additive evidence and falls back to manifest retrieval if the graph source is
empty, stale, missing, or raises.

## MCP graph tools

The MCP server still exposes graph-first tools (`opencontext_context`, search,
callers, callees, impact, node, files, status, trace) through
`opencontext_core.mcp_stdio.MCPServer`. MCP convergence onto the planner is a
later slice; this slice only unifies runtime context-pack candidate generation.

## CLI/API/workflows

CLI and API context-pack calls that use `OpenContextRuntime.build_context_pack()`
benefit from the planner path immediately. Direct MCP tool assembly and broader
workflow/harness phase context should be migrated in later SDD changes.

## Safety and budget gates

The planner is intentionally not the token-budget authority. It caps source
candidate counts and annotates provenance, while `ContextPackBuilder` remains the
hard token budget gate. Existing redaction, firewall, trace sanitization, and
omission metadata stay downstream of retrieval.
