# OpenContext — Product Roadmap

OpenContext is the verified-context runtime for AI coding agents: it indexes a
project into a knowledge graph, serves minimum-sufficient **verified** context
(gated, trust-scored, traceable) to whatever agent you already use, remembers
decisions across sessions, and keeps the developer in control — at the lowest
token cost.

This roadmap defines the full product surface, organized by capability. It is
the single source of truth for scope. It supersedes any prior planning notes.

## Principles

- **Configure, then get out of the way.** After setup there is nothing to learn;
  the agent you already use becomes better.
- **Advisory by default, strict on demand.** Gates, trust, and rules are
  recommendations the developer can escalate to hard blocks (CI, risky paths).
- **Minimum sufficient context.** Rank hard, compress losslessly, pack to a real
  token budget; never dump files.
- **Local-first.** Works offline, no API key required for the core.
- **Never clobber.** Every write into a user's files is a managed, reversible,
  idempotent merge with a backup.
- **One backend, many surfaces.** CLI, TUI, MCP, and HTTP share one core; they
  never drift.

## Current status (v0.4.0b0)

OpenContext Runtime v0.4.0b0 delivers a complete context engineering platform with:

- **SDD Orchestrator**: Full 8-phase lifecycle (explore → propose → spec → design → tasks → apply → verify → archive) with DAG state tracking, artifact stores (engram/openspec/hybrid), and per-phase model assignment via `SDDProfile`
- **Agent system**: Runtime agent orchestrator with pluggable skill-based agents and subagent spawning
- **LLM provider adapters**: OpenRouter, Anthropic, OpenAI, Local (Ollama), and Mock providers with unified adapter interface
- **Learning system**: Memory usability layer with context-aware retrieval and semantic reranking
- **Quality gates**: 7 built-in CI checks (security, quality, docs, performance, accessibility, dependencies, type safety)
- **Indexing pipeline**: Knowledge graph with SQLite+FTS5, call graph analysis, impact analysis, and framework route detection (19+ languages)
- **Interactive TUI menu**: 10-option main menu when `opencontext` is run without subcommand — Install, Upgrade, Sync, Configure Models, Create Agent, Plugins, SDD Profiles, Backups, Uninstall
- **Smart config discovery**: `opencontext.yaml` auto-discovered up to 10 parent directories; `opencontext config` without args launches wizard
- **Unified upgrade**: Single `opencontext upgrade` upgrades all OpenContext packages with per-package status table
- **Install script improvements**: pipx detection, PyPI-first path, source fallback, post-install verification
- **Security layer**: Secret redaction, provider policy enforcement, context firewall, prompt injection boundaries, air-gapped mode
- **Observability**: OTel-compatible tracing pipeline with metrics and logging
- **Context quality evaluation**: 5-dimension benchmark suite with ContextBench
- **Deep diagnostics**: `opencontext doctor deep` for runtime introspection
- **Plugin ecosystem**: Remote registry, GitHub installs, version pinning, checksum verification
- **Agent installer**: Support for 13+ AI coding agents with auto-detection and config generation
- **Memory layer**: Context repository with progressive disclosure, pinned memory, temporal memory, context DAG, session harvesting

## Capability pillars

### 1. Universal agent configurator
Make OpenContext install and configure the broad set of AI coding agents
without clobbering user files.

- Adapter registry keyed by an `Agent` enum; per-agent paths in one constants
  module; behavior expressed as **strategy enums** (system-prompt strategy, MCP
  config shape) so adding an agent never touches shared logic.
- `AGENTS.md`-first emission with named-file fallbacks where an agent requires
  its own file; optional symlink for stragglers.
- **Safe merge** in three modes: managed-block for co-owned Markdown
  (`<!-- opencontext:start --> … <!-- opencontext:end -->`), structured
  deep-merge for MCP config (JSON `mcpServers`, JSON `servers`, TOML
  `mcp_servers`, YAML), and own-the-file only for namespaced files we generate.
- Atomic writes (temp + rename, symlink refusal), timestamped backups with
  dedup + retention + pin, dry-run/diff, and rollback on failure.
- Skills and slash-command provisioning per agent.
- Consume the public MCP server registry as the neutral source, translate to
  each client shape.
- Lifecycle verbs: `install`, `sync`, `uninstall`, `restore`, `update`,
  `upgrade`, `doctor`.

### 2. Knowledge graph core
Best-in-class code intelligence as the substrate.

- **Structured symbol identity**: portable, version-aware symbol scheme
  (scheme · package · descriptor path); ingest external precise indexes where
  available instead of parsing every language ourselves.
- Multi-language extraction via tree-sitter with an explicit *degraded* status
  when no grammar is present (never silent regex-as-precise).
- **Incremental name resolution** via per-file partial paths stitched at query
  time — precise find-references / go-to-definition without a build system.
- Method/attribute and cross-file edge resolution, deterministic on ambiguity.
- **Task-relative ranking**: personalized PageRank over the def/ref graph with
  weight heuristics (boost task-mentioned and well-named symbols; downweight
  private and over-common ones).
- Modularity-based community detection and centrality-based hub detection.
- Real impact / blast-radius feeding a derived risk level.
- Fanout-bounded incremental indexing; mtime-keyed parse cache; watch service.
- Structural (meta-variable) query layer over the AST.

### 3. Verified context engine
Turn the graph into gated, trustworthy, cheap context.

- Graph-aware retrieval → ranked plan → token-aware pack.
- **Real tokenizer** budgeting (model-aware), not a character heuristic.
- **Signature-level compression**: keep declarations, elide bodies, on top of
  the existing text strategies.
- Budget fitting by measured iteration to a tolerance.
- Verification gates (coverage, freshness, provenance, budget, policy) with
  trust decision and a loadable trace for every request; advisory by default.
- AICX transport side-channel (deduplicated references + checksum) for
  tamper-evidence and a real reduction metric — never strips delivered content.
- Diff-as-evidence: working-tree / staged / branch diffs as first-class context.

### 4. Centralized memory
A local-first shared brain across agents.

- Engram-backed canonical store; one store for harvest-write and context-read.
- **Hybrid retrieval**: on-device embeddings + lexical + reciprocal-rank fusion
  with optional rerank, replacing lexical-only recall.
- **Write-time consolidation**: insert / supersede / delete / no-op so the store
  stays dense and current instead of accreting near-duplicates.
- **Bi-temporal supersession**: a superseded fact is marked invalid-as-of a
  timestamp and kept queryable, not deleted.
- Background consolidation pass that distills noisy session notes into a compact
  project brain off the hot path.
- Episodic memory: outcome-tagged successes/failures surfaced on similar tasks.
- Contradiction detection on write; security-mode redaction on read into context.

### 5. Agentic harness
The developer's control plane for change.

- A single orchestration spine over the development phases; real executors, no
  template-as-success.
- Honest apply (reports planned vs applied truthfully); approval checkpoint and
  test-first checkpoint before any write, driven by configuration.
- **Checkpoints**: snapshot before each apply step so approval becomes
  approve / inspect-diff / roll back.
- **Typed event ledger**: every step is an immutable action+observation event —
  replayable, pausable, the substrate for trust and trace.
- Config-driven gate dispatch; per-role / per-phase model routing via named
  profiles.

### 6. MCP surface
The agent's primary, verified interface.

- Read tools (search, context, callers, callees, impact, node, files, status,
  trace) routed through the verified pipeline (gates/trust/trace).
- **Symbol-level write tools** (replace-symbol-body, insert-before/after-symbol,
  rename) anchored to the graph, gated and traced at symbol granularity.
- Real, graph-derived risk on impact; firewall/redaction on every context-bearing
  response.
- Per-surface parity: CLI, MCP, and HTTP return the same verified result.

### 7. Experience
Simple by default, deep on demand.

- Zero-argument interactive TUI as the default surface: knowledge-graph status,
  verified-context-for-a-task with a trust badge and token-savings metric,
  harness/run progress, memory browser, backups/restore, model profiles.
- CLI hygiene: a small set of lifecycle verbs at the top level; domain
  capabilities grouped under namespaces; consistent flags
  (`--dry-run`, `--yes`, `--json`, `--quiet`) with flag > env > default
  precedence; side-effect-free info commands.
- First-run that ends with a concrete, copy-paste "try this now" using the
  developer's own indexed symbols.
- Honest, action-oriented diagnostics with remedies and a health rollup.

### 8. Foundations
- Single-file distribution with a stable integration contract (`mcp` server,
  `setup <agent>`, health endpoint, prebuilt releases) so any installer — or
  OpenContext itself — can wire it into an agent.
- Configuration is the one control plane governing memory, graph, rules, harness,
  gates, and self-improvement; validated against its schema.
- Self-improvement loop: observe outcomes, propose reversible configuration
  changes the developer approves; report realized vs projected savings.
- Security and redaction non-negotiable regardless of mode; everything reversible
  and idempotent.

## Execution order

**Tier 1 — complete, simple, drop-in.**
Universal agent configurator (1); zero-arg TUI + CLI hygiene + first-run (7);
single-file distribution + integration contract (8); finish in-flight wiring and
remove dead/duplicated code.

**Tier 2 — sharpen the depth.**
Knowledge-graph upgrades — structured symbol identity, incremental name
resolution, task-relative PageRank ranking, communities/centrality (2);
real tokenizer + signature compression (3); checkpoints + typed event ledger
(5); symbol-level write tools (6).

**Tier 3 — memory and polish.**
Hybrid memory retrieval, write-time consolidation, bi-temporal supersession,
background consolidation, episodic memory (4); per-role model routing; structural
query; advisory-gate defaults and self-improvement reporting (8).

## Next milestones

1. **Unified graph-aware retrieval**: Use one evidence planner across runtime context packs, MCP, CLI, API, workflows, and agents
2. **Parser-backed dependency graphs**: Deeper symbol extraction with cross-file type resolution and more accurate impact analysis
3. **Progressive and reversible compression**: Content-aware routing, exact-source retrieval handles, and cache-aligned output
4. **Production governed agent harness**: Replace mocked agent execution and prove parity or improvement against mature agentic workflows
5. **Optional semantic graph adapters**: SCIP first, then evaluated LSP, document/schema/IaC, and specialist security adapters
6. **Public-key workflow-pack signing**: Signed workflow packs with transparency log integration for supply-chain integrity
7. **Production provider SDK packages**: Published provider adapter packages (OpenAI, Anthropic, OpenRouter) outside core as documented extras
8. **Context quality GA**: Production-ready quality gates with configurable thresholds and CI integration
9. **Enterprise hardening**: Multi-user policy enforcement, hosted governance scaffolds, and org baseline distribution

See [Graph and Agent Integration Strategy](research/graph-and-agent-integration-strategy.md)
for the external-system review, integration boundaries, release phases, and
stability gates.

## Not yet enterprise ready

The design is enterprise-oriented, but certification, multi-user policy enforcement, hosted governance, and provider-specific production adapters are not complete. The security layer provides local guardrails and scaffolds that do not make the project a fully certified enterprise platform.

## Definition of done

- One command from zero to a configured agent with verified context working.
- The same verified result across CLI, MCP, and HTTP.
- Memory carries a decision from one run into the next.
- Multi-language impact returns real callers; ranking selects the right symbols
  under a token budget measured with a real tokenizer.
- Every write into a user's files is reversible and leaves their content intact.
- The full automated suite is green; behavior is demonstrated end to end.
