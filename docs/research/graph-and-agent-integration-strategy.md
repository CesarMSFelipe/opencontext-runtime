# Graph and Agent Integration Strategy

Status: research and architecture proposal  
Reviewed: June 12, 2026

## Objective

Make OpenContext the provider-neutral context layer that selects the smallest
useful evidence set for a coding task, while keeping the agent workflow at least
as capable as mature agentic workflow tools.

The target is not to install every graph product. The target is to combine the
best proven capabilities behind stable OpenContext interfaces, then prove that
each capability improves quality, token use, tool calls, latency, or safety.

## Current OpenContext Baseline

OpenContext already has:

- a local SQLite and FTS5 knowledge graph built from tree-sitter;
- call graph, path tracing, impact analysis, and framework route detection;
- MCP tools for search, context, callers, callees, impact, node, files, status,
  and trace;
- manifest retrieval, ranking, hard context budgets, compression, redaction,
  traces, ContextBench, memory, and an SDD harness.

The most important current gap is architectural:

- MCP graph exploration uses `indexing/context_builder.py`;
- runtime context packs use `retrieval/retriever.py`;
- `OpenContextRuntime._build_context_pack_with_trace()` does not currently use
  graph expansion.

Adding external graph engines before unifying those paths would create more
disconnected retrieval implementations. The first integration milestone must
therefore be a single graph-aware retrieval pipeline used by CLI, API, MCP,
workflows, and agents.

## Systems Reviewed

| System | Strong ideas to adopt | Integration decision |
|---|---|---|
| Graph-first exploration systems | One-call context, impact analysis, cross-language/framework links, file watching, explicit stale-result warnings, agent guidance that avoids redundant reads, benchmark by tokens/tool calls/cost/time | Adopt patterns and benchmark methodology. Consider optional adapters only after native graph retrieval is unified. |
| Multi-source graph systems | A graph that spans code, database schema, infrastructure, documents, and media; graph reports; optional export; parallel extraction through agent-native capabilities | Adopt the multi-source graph model and report/export concepts. Keep LLM-backed or multimodal extraction optional and outside core. |
| [Headroom](https://github.com/chopratejas/headroom) | Content-aware compression routing, AST compression, cache-aligned stable prefixes, reversible compression with retrieval on demand, cross-agent deduplication, evaluation of answer preservation | Implement provider-neutral equivalents in core interfaces. An optional bridge may be useful, but Headroom must not become a mandatory runtime dependency. Apache-2.0 license. |
| [Trellis](https://github.com/mindfold-ai/trellis) | Scoped specs, task-centered artifacts, project journals, auto-injected context, plan/implement/verify/finish loop, verification sub-agent, promotion of discoveries into shared specs | Adopt workflow behavior, not code. AGPL-3.0 means no code copying into the MIT core. |
| [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) | Local-first workspace, model fit recommendations, blind model comparison, deep-research runs, persistent skills and memory | Use as inspiration for a local evaluation lab and model-selection evidence. Do not absorb the workspace UI or AGPL code into core. |

## Other Relevant Systems

| System | Why it matters | Recommended use |
|---|---|---|
| [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) | Persistent graph, hybrid tree-sitter plus LSP resolution, fast indexing, infrastructure nodes, broad language support, structural-query benchmark | Primary comparison target for indexing speed, graph quality, structural queries, and token/tool-call reduction. Optional adapter candidate. |
| [Serena](https://github.com/oraios/serena) | Symbol-level retrieval and semantic editing backed by LSP or IDE analysis | Use LSP/SCIP-style semantic indexes as optional high-confidence enrichment sources. Editing remains outside OpenContext core. |
| [Aider repository map](https://aider.chat/docs/repomap.html) | Compact whole-repo map ranked over a dependency graph and constrained by an active token budget | Add graph centrality and task relevance to repo-map selection. |
| [SCIP](https://github.com/scip-code/scip) | Language-neutral protocol for precise definitions, references, and implementations | Preferred optional interchange format for precise semantic index imports. |
| [Joern](https://github.com/joernio/joern) | Deep code property graphs and data-flow analysis for security work | Optional specialist adapter for security workflows, never a default dependency. |
| [ContextBench](https://cioutn.github.io/context-bench/) | Gold-context recall, precision, and retrieval-efficiency evaluation | Align OpenContext benchmarks with process-level context quality, not token reduction alone. |

## Proposed Architecture

### 1. Unified evidence graph

Create provider-neutral contracts that normalize all retrieval sources:

```text
Native tree-sitter graph ─┐
SCIP/LSP index ───────────┤
Document/schema/IaC graph ├─> EvidenceGraph -> RetrievalPlanner -> ContextPack
Optional MCP/CLI adapters ┤
Memory and task artifacts ┘
```

Every evidence node and edge should record:

- stable identity and source location;
- source type, relationship type, and confidence;
- freshness and content hash;
- trust and data classification;
- token estimate and retrieval cost;
- adapter provenance and trace identifiers.

The native SQLite graph remains the default. External systems enrich it through
explicit adapters; they do not replace core interfaces or silently bypass
policy.

### 2. Query-aware graph retrieval

Replace the split retrieval paths with one planner:

1. Classify intent: locate, explain flow, change impact, implement, review,
   security, documentation, or cross-project.
2. Generate lexical, semantic, graph, memory, and task-artifact seeds.
3. Expand only relationships useful for the intent, such as callers, callees,
   routes, tests, schemas, configuration, or data flow.
4. Rank by task relevance, graph centrality, confidence, freshness, trust,
   diversity, and value per token.
5. Produce progressive-disclosure results:
   - compact graph summary first;
   - exact symbol snippets second;
   - full source or original compressed content only on demand.

CLI, API, MCP, workflows, and agent adapters must use this same planner.

### 3. Freshness and trust

Graph-derived context saves tokens only when agents can trust it without
re-reading files.

Required behavior:

- incremental indexing or bounded reconciliation on connection;
- content hashes per source;
- explicit stale/pending banners in every affected result;
- fail-open to direct file reading when a source is stale;
- no silent answer from an uncertain or stale graph;
- trace records for adapter, graph version, freshness, and omitted evidence.

### 4. Content-aware and reversible compression

Evolve compression from one configured strategy into a content router:

- code and signatures: AST-aware pruning;
- structured data: schema/key-aware compaction;
- logs: repetition collapse while preserving errors and surrounding evidence;
- prose and docs: extractive compression;
- graph output: compact nodes and typed edges;
- stable prefix ordering for provider cache reuse.

Lossy compression must remain traceable. Originals should be addressable through
short retrieval handles so an agent can request exact evidence when needed.
Protected spans, secrets, policy boundaries, and high-risk evidence must remain
uncompressed or use lossless compaction.

### 5. Agentic harness equal to or better than mature workflow tools

Mature agentic workflow tools are currently stronger at projecting a coherent workflow into many
native agent platforms. It provides automatic skill discovery, isolated
phase-specific sub-agents where supported, persistent artifacts, per-phase model
routing, and a low-friction setup experience.

OpenContext is already stronger in graph context, token accounting, safety
policy, traceability, quality gates, and runtime control. To be equal or better
as an agentic system, OpenContext must add:

- one task classifier that chooses direct execution or governed SDD;
- isolated phase contexts with explicit input/output contracts;
- native delegation adapters when the host supports sub-agents and a reliable
  inline fallback when it does not;
- automatic skill discovery scoped by task and project;
- graph-built context packs for every phase;
- bounded self-fix loops in verify/review;
- artifact and memory promotion at finish/archive;
- per-phase model-role routing based on measured quality, cost, and privacy;
- resumable runs, deterministic gates, and complete evidence receipts.

The legacy `AgentOrchestrator` cannot be considered production-ready while
agent creation and execution remain mocked. The governed `HarnessRunner` and SDD
runtime should become the production orchestration path instead of creating a
third competing agent path.

## Integration Boundaries

Core remains:

- Python, provider-neutral, local-first, deterministic by default;
- free of FastAPI, CLI frameworks, SDKs, LangChain/LlamaIndex, vector-database,
  Docker, Kubernetes, and external graph-engine assumptions;
- deny-by-default for network, writes, providers, and native tool adapters.

External integrations must be optional packages, plugins, or subprocess/MCP
adapters with:

- explicit capability declarations;
- license and provenance metadata;
- time, memory, output, and token limits;
- sanitized and schema-validated output;
- freshness reporting;
- no direct access to protected sinks.

AGPL projects may inform behavior and interoperable contracts, but their code
must not be copied into the MIT-licensed core.

## Delivery Plan

### Release A — Native graph retrieval convergence

1. Introduce `EvidenceNode`, `EvidenceEdge`, `EvidenceBundle`, and
   `RetrievalSource` contracts.
2. Make runtime context packs use graph-aware retrieval.
3. Replace duplicate MCP context assembly with the unified planner.
4. Add graph centrality, intent-specific expansion, diversity, and
   value-per-token ranking.
5. Add freshness metadata and stale-result behavior.
6. Add gold-context cases for structural, implementation, review, and impact
   questions.

### Release B — Compression and progressive disclosure

1. Add content-type routing.
2. Add reversible retrieval handles.
3. Add structured-data, log, code, and graph compactors.
4. Add stable ordering and cache-alignment reports.
5. Prove answer/source preservation under each compression strategy.

### Release C — Optional semantic and specialist adapters

1. Define adapter protocol and conformance tests.
2. Build SCIP import first.
3. Evaluate LSP/Serena-style enrichment.
4. Evaluate external graph adapters against native retrieval.
5. Add Joern only for opt-in security workflows.
6. Add document/schema/IaC graph enrichment inspired by multi-source graph systems.

### Release D — Production agentic harness

1. Retire or replace mocked agent execution.
2. Unify SDD runtime, harness gates, skills, memory, and model routing.
3. Add host-native delegation adapters and inline fallback.
4. Add resumable bounded self-fix loops.
5. Benchmark against a mature agentic workflow on identical tasks.

### Release E — Self-hosted evaluation lab

1. Add local model-fit reporting and blind comparison runs inspired by
   Odysseus.
2. Add deep-research workflow evidence packs.
3. Use OpenContext itself as the first long-running dogfood project.

## Stability and Benchmark Gates

OpenContext should not claim an integration is stable because it reduces input
size. It is stable only when quality, freshness, safety, and operability also
pass.

Required release evidence:

| Area | Gate |
|---|---|
| Context quality | No regression in expected-source coverage; publish recall, precision, and forbidden-source hits |
| Token efficiency | Report median and tail input tokens against current OpenContext and file-read baselines |
| Agent efficiency | Report tool calls, repeated reads, wall time, and model cost where available |
| Answer/task quality | Structural question correctness and implementation/verification success must be equal or better than baseline |
| Freshness | Modified sources never produce silently stale graph answers |
| Safety | Redaction, classification, provider policy, and trace hygiene remain passing |
| Determinism | Repeated local/mock runs produce stable source selection and gate results |
| Licensing | Adapter and copied-code audit passes |
| Operations | Focused tests, full `pytest`, Ruff, formatting, mypy, doctor, and verify pass |

The first dogfood suite should run on OpenContext Runtime itself and compare:

1. current manifest/file retrieval;
2. unified native graph retrieval;
3. native graph plus each optional adapter;
4. graph retrieval plus progressive compression;
5. direct/inline agent workflow versus delegated governed workflow.

No external adapter should be enabled by default unless it wins on a documented
quality-efficiency frontier and preserves OpenContext's security defaults.
