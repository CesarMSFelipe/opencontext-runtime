# Memory System

OpenContext maintains a 7-layer memory that enriches every context pack with past
experience. Two coexisting modes cover the agent-host space:

* **OpenContext-only mode** (default) — every layer runs locally on SQLite+FTS5.
  No external services, no API keys, no network. Works the moment the runtime is
  started.
* **OpenContext + Engram opt-in mode** — durable layers (`semantic`, `episodic`)
  route to a co-resident **Engram** install when one is configured to be reached;
  `procedural`, `failure`, `working`, `project`, and `harness_experience` always
  stay local. Engram is **opt-in** — it never engages implicitly and OpenContext
  falls back to local memory for every layer whenever Engram is not configured,
  not reachable, or configured to be skipped (`air_gapped` security policy).

Pick the mode that fits your deployment; the local-mode default is the right
choice for the vast majority of installs. The agent-facing MCP server advertises
all four `opencontext_memory_*` tools regardless of mode, but availability is
gated on a live runtime — agents must check the memory status before relying on
memory (see [Availability](#availability)).

## Five Layers

| Layer | What it stores | Persists |
|-------|---------------|---------|
| `SEMANTIC` | Stable project facts: "repo separates core from CLI" | Across sessions |
| `EPISODIC` | Past experiences: "task X failed because graph_db.py was missing" | Across sessions |
| `PROCEDURAL` | Learned rules: "for KnowledgeGraph changes, always read graph_db.py too" | Across sessions |
| `WORKING` | Current task context | Cleared after archive |
| `FAILURE` | Failure patterns: symbols and files that caused test failures | Across sessions |

## How Memory Enriches Context

1. At **explore**, the runtime queries PROCEDURAL + FAILURE layers for the current task
2. Relevant memories become part of the ContextContract (`required_memories`)
3. Symbols linked to past failures get a boost in the 9-signal retrieval scorer
4. Procedural rules inject known required symbols before retrieval starts

## Availability

The `opencontext_memory_*` MCP tools (`opencontext_memory_save`,
`opencontext_memory_search`, `opencontext_memory_context`,
`opencontext_memory_judge`) are advertised in the default tool allowlist on
every server, but they are NOT guaranteed to succeed. Availability depends on
the live runtime wiring:

* **Runtime-backed MCP server** — `opencontext_status` returns
  `memory.available=true` plus the backend kind (`local` or `composite`) and
  the Engram-vs-local layer split. Save/search/context persist and retrieve
  records.
* **Raw MCP server (no runtime)** — every memory tool returns
  `available=false` with reason `memory backend unavailable; start the
  runtime-backed MCP server`. The MCP catalog still names the tools, but the
  data plane is empty.

Agents must check `opencontext_status.memory.available` (or catch the
`available=false` response from the first save call) before relying on memory.
Just because the memory tools appear in `tools/list` does not mean memory
persists on every install — the runtime wires the actual backend.

## Hybrid Retrieval Scoring — Memory Signals

Two of the nine retrieval signals come directly from memory:

- `memory_confidence` (weight 0.10) — confidence of linked memory records
- `recent_failure` (weight 0.08) — failure boost from FAILURE layer records

A symbol that caused a test failure in a past run of a similar task will score higher in retrieval — automatically, without any configuration.

## Memory Harvesting

After every archive phase, `MemoryHarvester` runs automatically:

1. **Episodic record** — what the task was, what happened, outcome
2. **Procedural rules** — extracted from failures: which files were missing, which symbols were unexpectedly required
3. **Failure patterns** — symbols linked to test failures via `BROKE_BEFORE` graph edges
4. **Contradiction detection** — new records are checked against existing ones; conflicts are flagged

```bash
opencontext memory harvest              # harvest from latest run
opencontext memory harvest --from-trace last
```

## Memory Decay

Records age by half-life. Default: 90 days. Stale records are pruned at GC.

```yaml
# opencontext.yaml
memory:
  decay:
    enabled: true
    default_half_life_days: 90
```

```bash
opencontext memory gc --dry-run         # preview what would be pruned
opencontext memory gc                   # prune stale records
```

## Confidence Lifecycle

| Event | Effect on confidence |
|-------|---------------------|
| Written | 1.0 (default) |
| Reinforced | +0.1 (max 1.0) |
| Contradicted | −0.2 |
| Failure boost | +0.15 per failure (max 1.0) |
| Decay | −half_life per 90 days |

## CLI

```bash
opencontext memory search "auth middleware failures"
opencontext memory harvest
opencontext memory gc --dry-run
opencontext memory list
opencontext memory show <id>
```

## Storage

Local memory lives in `.opencontext/memory.db` — a SQLite file with an FTS5 virtual table for full-text search. The schema mirrors the knowledge graph for consistency.

### Provider

```yaml
memory:
  provider: auto   # auto | local | engram
```

- `auto` (default) — couple to a co-resident **Engram** install if one is detected, otherwise use the local store for every layer.
- `local` — always use the local SQLite store for every layer (OpenContext-only mode).
- `engram` — force coupling (use the local store only if Engram cannot be reached). Requires explicit configuration; this is the OpenContext + Engram opt-in mode.

When coupled, `CompositeMemoryStore` routes by layer: **EPISODIC/SEMANTIC → Engram**, **PROCEDURAL/FAILURE/WORKING/PROJECT/HARNESS_EXPERIENCE → local SQLite** — no duplication. Engram is reached through its CLI (writes) and its on-disk store (reads); nothing is sent over the network. In `air_gapped` security mode the coupling is always force-degraded to local.

### Falling back when Engram is unavailable

The OpenContext + Engram mode falls back to local memory explicitly:

* If `engram` is configured but no client is reachable, `CompositeMemoryStore.write`
  transparently persists the record locally (a `degraded=true` flag is returned
  with the save).
* In `air_gapped` security mode, Engram coupling is force-disabled; every layer
  is local.
* If an agent calls a memory tool on an MCP server that has no runtime
  attached, the tool returns `available=false` with the actionable reason
  `memory backend unavailable; start the runtime-backed MCP server` (no
  layer is ever silently dropped).

Live Engram is opt-in only — it never engages automatically and must be
explicitly configured to couple a `semantic` or `episodic` write through it.

Detection and targets can be overridden with `OPENCONTEXT_ENGRAM` (`0`/`1`), `OPENCONTEXT_ENGRAM_DB`, and `OPENCONTEXT_ENGRAM_PROJECT`.

## UnifiedGraph Integration

Memory records are not isolated — they connect to code symbols via the UnifiedGraph:

| Edge | Meaning |
|------|---------|
| `BROKE_BEFORE` | Failure pattern → code symbol |
| `FIXED_BY` | Fix trace → code symbol |
| `APPLIES_TO` | Procedural rule → code symbols it governs |
| `SUPERSEDES` | Newer memory record → older one |
| `REINFORCES` | Evidence → memory record |

When retrieval expands neighbors of a code symbol, memory-linked nodes appear alongside code neighbors.

## Related

- [Session Harvesting](./session-harvesting.md)
- [Temporal Memory](./temporal-memory.md)
- [Unified Graph](../architecture/overview.md)
- [Retrieval Scoring](../architecture/context-pack-builder.md)
