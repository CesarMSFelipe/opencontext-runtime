# KG_CONTEXT_COMPRESSION_CONTRACT

The knowledge graph exists to save tokens and improve decisions, not just to find symbols.
The context pack engine must produce small, useful, verifiable packs with measurable savings.

Verified by: AC-005..AC-008, AC-020, AC-021, KG-001..KG-008, CTX-001..CTX-008, SMOKE-004,
SMOKE-005.

## KG minimum node set

`file`, `symbol`, `test`, `module`, `command`, `config`, `memory`, `run`, `sdd_artifact`,
`decision`, `risk`.

## KG minimum edge set

`defines`, `calls`, `imports`, `tests`, `covers`, `modified_by`, `mentioned_by`, `depends_on`,
`configured_by`, `related_to_memory`, `produced_by_run`.

Minimum proof: on the basic fixture the KG demonstrates at least one `test —tests→ symbol`
edge (KG-002) and never indexes caches/ignored paths (KG-005).

## Query surface

Real:

```
opencontext knowledge-graph search | query | context | callers | callees
                            | impact | node | status | rebuild   (also: trace, view, migrate)
```

Planned additions (target):

```
opencontext knowledge-graph related-tests <file-or-symbol> --json
opencontext knowledge-graph explain-pack --run <run_id> --json
```

> Current → Target: `related-tests` is derivable from `tests`/`covers` edges; `explain-pack`
> replays why each pack item was selected for a given run. Until they land, `impact` and
> `pack` explanations (`explain` command) are the closest surfaces.

## Incremental indexing duties

After a file change, incremental indexing must detect: new files, deleted files, modified
symbols, related tests, obsolete edges (removed, not duplicated), and memory linked to touched
nodes — without a full rebuild unless required (AC-020, KG-004). Real entry points:
`index --incremental`, `knowledge-graph rebuild`.

## Pack pipeline

```
task understanding → workspace scan → KG candidate expansion → memory recall
→ test discovery → ranking → budget allocation → protected span detection
→ compression → pack generation → metrics
```

Ranking factors (initial weights): direct task match 0.30, KG neighborhood 0.25, related tests
0.15, recency 0.10, linked memory 0.10, centrality 0.05, size penalty −0.05.

## Protected spans (never compressed aggressively)

- function signatures
- imports
- test assertions
- public interfaces
- relevant configuration
- errors and stack traces
- fragments referenced by memory or KG
- recent changes

Compression must fail rather than drop a mandatory protected span (CTX-005).

## Mandatory pack metrics JSON

Every pack (and every run's `context-pack.json`) reports:

```json
{
  "context": {
    "budget_tokens": 24000,
    "input_tokens_estimated": 81200,
    "output_tokens_estimated": 18500,
    "compression_ratio": 0.22,
    "kg_nodes_used": 12,
    "kg_edges_used": 18,
    "memory_hits": 3,
    "protected_spans": 9,
    "protected_spans_kept": 9,
    "excluded_files": 42
  }
}
```

Rules: the pack must be able to explain inclusion/exclusion per file (CTX-006, `explain`
command); a large project never gets fully packed (CTX-007); under a low budget the engine
compresses and keeps protected spans intact (AC-021).

> Current → Target: `pack` exposes `--query`, `--max-tokens`, `--format json` (target: honor
> the global `--json` flag). The metrics block above is the freeze target; current pack output
> reports budget/usage but not the complete block (notably `protected_spans_kept` and
> `kg_edges_used`), and `memory`/`run`/`decision`/`risk` node kinds are target additions to the
> current code-centric node set.
