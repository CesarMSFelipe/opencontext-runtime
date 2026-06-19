# OpenContext — Full Systems Review

A cross-system architecture, code-quality, and product review covering memory, KG,
retrieval, compression, the agentic harness, the CLI/config surface, and the
plugin/skill/persona/agent ecosystem. Findings are evidence-backed (`file:line`)
and severity-tagged (**HIGH / MED / LOW**). Produced from a parallel deep read of
the whole `packages/` tree on branch `feat/engram-coexistence`.

---

## TL;DR — the one thing to take away

**The components are individually well-built; the failures are at the seams.**
Almost every subsystem scores well in isolation — clean Pydantic contracts, real
call-graph traversal, fail-closed security, lossless compression primitives,
honest "scaffold" labeling that never reports a stub as success. But a large
fraction of the advertised capability is **implemented yet unreachable from the
production runtime path**: FTS and vector retrieval, memory-aware ranking, the
"code that broke before gets boosted" loop, real LLM execution, CCR reversible
compression, cache alignment, per-phase models, personas, skills — all exist and
are tested, yet are not wired into the live flow.

On top of that, the headline concern is real: **the default memory provider
silently outsources OpenContext's own memory engine to a co-resident external
tool (Engram) whenever one is present on the machine.**

The work ahead is mostly *connecting and consolidating what already exists*, not
building new things.

---

## Headline findings (severity-ranked, several independently cross-validated)

| # | Severity | Finding | Evidence |
|---|----------|---------|----------|
| 1 | **HIGH** | `memory.provider: auto` default couples to Engram when present → OC's own EPISODIC/SEMANTIC memory is bypassed for a lossy bridge | `config.py:602`, `factory.py:90-116`, `engram_bridge.py:66-82`; live: store resolves to `CompositeMemoryStore` |
| 2 | **HIGH** | Production context-pack planner is built with the **bare constructor**, no `from_config`, no `memory_store` → FTS, vector/semantic retrieval, and memory-aware ranking are all **dark** | `runtime.py:766` (`RetrievalPlanner(manifest, graph_db_path=...)`) vs unused `planner.py:245 from_config` *(found by 2 reviewers)* |
| 3 | **HIGH** | No real LLM provider can be wired through config — `_gateway_from_config` returns a mock for `mock` and **raises** for everything else; `providers/adapters.py` is never bridged to `LLMGateway` | `runtime.py:846-850`; `providers/adapters.py` has no `LLMGateway` implementor |
| 4 | **HIGH** | Per-run memory harvest is **dead code**: imports `opencontext_core.memory.collector` (module does not exist), calls `repo.save` (no such method), all under `except Exception: pass` | `harness/runner.py:503-517` (note the `# type: ignore[import-not-found]`) *(found by 2 reviewers)* |
| 5 | **HIGH** | Memory write-path and read-path use **different files and different providers**: harvester writes local SQLite at `.opencontext/memory.db`, runtime reads `auto`→Engram at `.storage/opencontext/memory.db` → harvest→recall loop cannot close | `runner.py:110-113`, `runtime.py:179`, `factory.py` |
| 6 | **HIGH** | **Three** agent-file generators + **three** target enums; install flows run two of them against the same files | `adapters/agent_manifest.py`, `configurator/service.py:288`, `agent_installer.py:22,92` *(found by 2 reviewers)* |
| 7 | **HIGH** | Plugin loading is unsandboxed `exec_module` with no permission check; the deny-by-default `PluginManifest` model has **zero importers** | `plugin_system.py:982-989`, `plugins/manifest.py:24` |
| 8 | **HIGH** | Config bridge maps only **4 of 24** settable keys to the runtime YAML → ~20 `config set` keys are silently inert | `config_sync.py:17-22`, `config_cmd.py:117-147,195-196` |
| 9 | **HIGH** | **Four** overlapping setup paths (`init`, `onboard`, `install`, `setup`) — `install` re-implements onboarding inline rather than calling `OnboardingService.run()` | `main.py:1462,1731-1866,2082`, `setup_cmd.py:198` |
| 10 | **HIGH** | Indexing hot loop swallows per-file errors silently → a broken parser looks like a successful index, corrupting the KG with no trace | `indexing/project_indexer.py:82-99` |
| 11 | **MED-HIGH** | `verify_context` gates **annotate but do not enforce** — a failed coverage/provenance/policy gate still returns the full context | `runtime.py:617-650,1090`; AICX validator downgrades to warning `validator.py:48` |
| 12 | **MED-HIGH** | Two parallel SDD orchestrators (`HarnessRunner` vs `WorkflowEngine` SDD steps) plus a third unused (`SDDOrchestrator`); same vocabulary, incompatible semantics | `harness/runner.py:82`, `workflow/steps.py:152-329`, `agents/sdd_orchestrator.py:102` |

---

## 1. Memory — the priority concern

> **Reproduction.** With the shipped default `memory.provider: auto` and a
> co-resident Engram present, `BackendFactory.create_memory_store(config, path)`
> resolves to `CompositeMemoryStore`. `detect_engram()` returns `True` whenever the
> `engram` CLI is on `PATH` **or** `~/.engram/engram.db` exists. So the project's
> own memory is bypassed by an *environmental accident*, not a user decision.

### 1.1 There are effectively three memory stores plus Engram

| Subsystem | Backend | Role | Real consumers |
|---|---|---|---|
| `memory/graph.py` `LocalMemoryStore` + `backends.py` | SQLite + FTS5 | Canonical agent memory: 5 cognitive layers, decay/reinforce/contradict, consolidation, bi-temporal supersede, hybrid recall | harvester (write), runtime read-path, CLI `memory maintain/review` |
| `memory_usability/context_repository.py` | Markdown + YAML frontmatter | Human-readable redacted memory, keyword/entity scoring, pin, GC | CLI `memory list/search/expand/gc/prune`, runtime read-path |
| `memory/engram_mcp_store.py` + `engram_bridge.py` | Engram (CLI write, SQLite `LIKE` read) | EPISODIC/SEMANTIC when coupled | `CompositeMemoryStore` only |
| `memory/stores.py` `LocalProjectMemoryStore` | JSON | Project manifest (index output) — unrelated | `runtime.index_project` |

`LocalMemoryStore` (SQLite) and `ContextRepository` (markdown) **independently
re-implement the same job**: storage, keyword search, supersede, expiry/GC,
confidence/priority, entity scoring (`graph.py:206-374` vs
`context_repository.py:85-218`). No shared schema, no shared IDs, never
reconciled. Three incompatible taxonomies coexist (5 `MemoryLayer` enum values vs
`ContextRepository`'s free-form `kind` vs Engram's two types).

### 1.2 What `auto`→Engram actually bypasses (HIGH)

When Engram is selected, EPISODIC + SEMANTIC route to `EngramMemoryStore`, which
discards almost everything OC built:

- `decay()` returns 0 — no aging (`engram_mcp_store.py:185-187`).
- `reinforce`/`contradict` are best-effort `mem_update` calls that **no-op
  entirely** under the CLI client (which has no `mem_update`) — `engram_mcp_store.py:165,176`.
- No consolidation, no bi-temporal supersede, no hybrid/semantic recall, no FTS5;
  Engram reads are bare `LIKE` over title/content (`engram_bridge.py:140-156`).
- Writes lossily collapse the layer to two Engram types; confidence is hard-set to
  1.0 on read (`engram_bridge.py:44,133`).

If Engram is **absent**, everything degrades cleanly to `LocalMemoryStore`
(`factory.py:106-108`). The asymmetry is the whole problem: a more-capable engine
is silently downgraded to a less-capable bridge based on what happens to be
installed.

### 1.3 The harvest→recall loop is broken three ways

- **Write path ≠ read path file.** Harvester writes `root/.opencontext/memory.db`
  (`runner.py:110-113`); runtime reads `.storage/opencontext/memory.db`
  (`runtime.py:179`). Different files.
- **Write path ≠ read path provider.** Harvester is hard-wired `provider:"local"`
  (`runner.py:112`); the reader uses `auto`→Engram. Writes land in local SQLite;
  EPISODIC/SEMANTIC reads come from Engram.
- **"Reconciliation" is concatenation.** The runtime merge excludes overlapping
  `memory:{id}` (`runtime.py:668-672`), but IDs never overlap across stores, so
  nothing is actually deduped/merged.

### 1.4 Dead and unwired memory code

- `_post_run_update` auto-harvest is **entirely dead**: imports the non-existent
  `memory.collector`, calls `MemoryCandidateExtractor.extract_from_run` (real
  class only has `extract`), and `repo.save` (only `store` exists) — all masked by
  `except Exception: pass` (`runner.py:503-517`). Automatic post-run memory
  capture has never run.
- `RetrievalPlanner` accepts and gates on `memory_store`, but the runtime builds it
  **without** one (`runtime.py:766`), so memory→retrieval enrichment silently
  no-ops in the context-pack path (the harness path does inject it — inconsistent).
- `failure_boost` is implemented on both stores and the protocol but has **no live
  caller** — failure memories never reweight retrieval.
- Documented-but-unwired: `ProgressiveDisclosureMemory`, `TemporalMemoryGraph`,
  `ContextDAG`, `NoveltyGate`, `SessionMemoryRecorder` (zero external consumers).
- No bulk export/import between OC-local and Engram (per-query coupling only).

### 1.5 Recommendation (memory)

1. **Default to `local`; make Engram explicit opt-in.** Change
   `MemoryPolicyConfig.provider` default `auto → local` (`config.py:602`). Keep
   `engram`/`auto` as deliberate choices. This is the single highest-value fix and
   directly answers the concern. *(Small, safe, high-impact.)*
2. **One store, one path, one provider.** Route harvester, runtime reader, and CLI
   through a single `create_memory_store(config, storage_path)` at one path
   (standardize on `.storage/opencontext/memory.db`); delete the hard-coded
   `provider:"local"` shim and the second storage root in `runner.py:110-112`.
3. **Collapse `memory_usability` into a rendered view.** Make `LocalMemoryStore`
   (SQLite) the single source of truth; reduce `ContextRepository` to a read-only
   markdown projection/exporter — removing the parallel store/search/GC/supersede,
   the dual-write, and the divergent lifecycles.
4. **Delete or rewrite the dead harvest** (`runner.py:502-518`) against real APIs
   (`extract` + `store`); tighten the `except` to log.
5. **Wire the planner's memory_store** (see §2) or remove the half-wired path.
6. **If Engram coupling stays**, give the bridge a real `mem_update` (so
   reinforce/contradict aren't silent no-ops) and a one-shot export/import.

---

## 2. KG / Retrieval / Compression

Individually strong (clean contracts, real graph traversal, lossless SmartCrusher,
caller-owned CCR). **Roughly half the advertised retrieval/compression capability
is unreachable from the runtime.**

### 2.1 The production planner uses the bare constructor (HIGH)

`runtime.py:766` builds `RetrievalPlanner(manifest, graph_db_path=...)`, so only
`ManifestRetrievalSource` + `GraphRetrievalSource` run. `FTSRetrievalSource`,
`VectorRetrievalSource`, and `memory_store` are attached **only** in
`RetrievalPlanner.from_config` (`planner.py:245`) — which has **zero production
callers**. Consequences:

- BM25/FTS and semantic/vector retrieval are dark, though fully implemented
  (`planner.py:88-204`). RRF fusion rarely fires (only 1-2 sources return).
- The flagship KG↔memory↔retrieval loop is dead at the seam: `memory_boost_map`
  default is always empty (`planner.py:334`), `UnifiedGraph` is built with
  `persist=False` so `BROKE_BEFORE` failure→symbol edges are never traversed,
  `include_memory` stays False (`planner.py:454`).

### 2.2 Gates annotate, they do not enforce (MED-HIGH)

`verify_context` computes gate pass/fail and flips `trust_decision` to
"insufficient" on failure (`runtime.py:617-618`), **but still returns the full
context** (`runtime.py:638-650`). A failed coverage/provenance/policy gate does
not redact, withhold, or truncate. The AICX validator likewise downgrades a
missing security gate on a high-risk request to a *warning*, not an error
(`validator.py:48`). A caller trusting `gates[].passed` to mean "safe to use" is
misled.

### 2.3 Other gaps

- **AICX round-trip is lossy for non-protected evidence** by design: non-protected
  items decode to `""` (`decoder.py:60-64`), and the fidelity metric only checks
  **count parity, not content** (`metrics.py:22`). Safe today (decoded plan is
  discarded) but a trap for any future decode-to-rebuild consumer.
- **CCR reversible compression is never wired** — `AICXCompiler().compile(plan)` is
  always called with no `ccr_backend` (`runtime.py:488,522,791`). (Global state
  *was* correctly removed — verified.)
- **CacheAligner is never attached** in the runtime (`PromptAssembler()` with no
  aligner, `runtime.py:901`); `is_cache_hit` is a hardcoded `return False`
  (`cache_aligner.py:223`).
- **The local embedding generator carries no semantic signal** — it is a
  SHA256-seeded PRNG (`generators.py:13-51`); external embedding providers raise
  (`generators.py:104`); `embedding.enabled=False` by default. So even if vector
  retrieval were wired, it would be near-random locally.
- **Compression is salvage, not strategy** — `ContextPackBuilder.pack` only
  compresses items that overflow the budget (`packing.py:53`); `compress_items`
  (proactive, fit-more-evidence) is effectively unused.
- **Layering**: `context/compression.py:55` still imports `ContentRouter` from
  `memory_usability` (lazy, guarded) — the previously-flagged sideways edge
  remains.

### 2.4 Recommendation (KG/retrieval/compression)

1. **Switch `runtime.py:766` to `RetrievalPlanner.from_config(manifest, config,
   storage_path=..., memory_store=self.memory_store)`** — this single change lights
   up FTS, vector (when enabled), and memory-aware ranking at once. *(Highest
   leverage in this area.)*
2. Build a `memory_boost_map` from failure records; pass `persist=True` to
   `UnifiedGraph` so memory↔symbol links load.
3. Make gates enforce (withhold/flag-omit on failure) **or** rename `passed →
   advisory` and document that callers must enforce.
4. Make packing proactively compress to fit more distinct evidence per token.
5. Compare AICX content (hash per evidence id), not `len()`, in the fidelity
   metric; wire `ccr_backend` if the reversible path is meant to be live.
6. Replace the PRNG embedding with a hashing/char-ngram TF-IDF (real local
   signal) or clearly mark it test-only.
7. Delete dead surfaces: `AdaptiveCompressionController`, `bridge_enrichment`,
   `context/providers.py` scaffolds, unused `_cache_aligner`/`_output_reducer`
   fields.

---

## 3. Agentic / Harness / Workflow

The orchestration *runs* end-to-end (all 9 phases, artifacts, gates), and the
degradation messaging is honest. But the agentic loop produces little real work
because the most important seams are unwired.

### 3.1 Three orchestrators, one canonical (MED-HIGH)

- **`HarnessRunner`** (`runner.py:82`) — canonical, file/artifact spine. Every real
  caller uses it (CLI loop, `main.py`, boundary, verification).
- **`WorkflowEngine` SDD steps** (`steps.py:152-329`) — a second SDD pipeline over
  *context items* (not files); `context_apply` is an explicit "scaffold" that
  writes nothing. Redundant with HarnessRunner. Its non-SDD `code_assistant` path
  is the only part worth keeping.
- **`SDDOrchestrator`** (`sdd_orchestrator.py:102`) — a third; HarnessRunner imports
  only its DAG constants and re-implements scheduling. The class itself is unused
  by the harness path.

### 3.2 No real provider reachable (HIGH)

`_gateway_from_config` returns a mock for `mock` and **raises** for every other
provider (`runtime.py:846-850`). `providers/adapters.py`
(Anthropic/OpenAI/OpenRouter/Local) is never bridged to the `LLMGateway` protocol,
and no caller injects a gateway. Net: with stock config the executor is always
absent → SPEC/DESIGN/TASKS/APPLY always emit static scaffolds and warn "configure
a provider". This is *the* reason the loop only produces stubs.

### 3.3 The work loop doesn't close

- **APPLY never writes code** — `ApplyPhase` can write, but `state.apply_edits` is
  never populated by any caller and nothing converts text artifacts → `FileEdit`s.
  APPLY always reports `status="planned"`, zero filesystem mutation.
- **VERIFY runs the whole suite** — with no changed files it falls back to
  `pytest <root>` (`phases.py:1424`), 120s, every loop; failures only warn.
- **Token budget enforcement is not real** — `TokenBudgetEnforcer` is constructed
  and never used; every phase except explore hardcodes `used_tokens=0` (10 sites).
- **Several declared gates are never bound** — `trace_id_created`,
  `included_sources_present`, `review_artifact_created`, etc. return `None` in the
  dispatcher (`runner.py:692-725`).
- **`ConfidenceGate` essentially never blocks** — a heuristic on prior gate
  pass-rate, tuned so apply passes whenever ~half of prior gates passed.
- **Checkpoint machinery is solid but approval UX is dead** — `approved_phases` is
  never supplied and the CLI loop's `_ask_continue` is **defined but never called**,
  despite the "user checkpoints" docstring.
- **Context pack never reaches the LLM** — the executor prompt sends only `task` +
  phase name (`executor.py:42`); the verified context pack/contract built in
  explore is written to disk and never injected.
- **Per-phase models are inert** — `state.current_phase_model` is set but never read.
- **Three KG db filenames** — `graph.db` (explore impact), `context_graph.db`
  (runtime), `knowledge_graph.db` (re-index) — so impact analysis usually finds
  nothing.

### 3.4 Recommendation (agentic)

1. **Bridge providers→gateway** (highest leverage): an `LLMGateway` adapter over
   `providers/adapters.py`, built by `_gateway_from_config` for real providers.
2. **Retire the WorkflowEngine SDD pipeline**; keep only `code_assistant`. Fold or
   delete `SDDOrchestrator`. One orchestrator.
3. **Close artifact→edit→apply** (emit `FileEdit`s; populate `apply_edits`).
4. **Repair or delete the dead harvest** (`runner.py:495-518`).
5. **Make budget/gates real**; bind or remove declared-but-unbound gates.
6. **Unify the KG db path**; feed the context pack + memory into executor prompts;
   actually call `_ask_continue` (or drop the checkpoint claim).

---

## 4. CLI / Config / Security

Security is the **strongest** part of the codebase. The liabilities are coherence:
overlapping setup paths, inert config keys, an oversized surface.

### 4.1 Security is real, not cosmetic (LOW concern)

Tool deny-by-default with a `DENY` fallback (`security/permissions.py:38`),
write/network denied without explicit permission (`tools/policy.py:92-120`), wired
into the MCP server, tool registry, and harness. Redaction is genuine at the
context sink (`safety/redaction.py`, `context/assembler.py:61-85`). Provider policy
is fail-closed (`safety/provider_policy.py:37-88`) and reached via the firewall on
trace persist + context export. **Caveat (MED):** the MCP server's *default* policy
allowlists every tool it exposes (`mcp_stdio.py:117-119`), so out-of-the-box MCP
is allow-all, not deny-by-default — and `doctor security` asserts this as a pass.

### 4.2 Config coherence (HIGH)

- **20 of 24 settable keys are inert.** `config_cmd.CONFIG_PATHS` exposes 24 keys
  but `config_sync.RUNTIME_PREF_TO_YAML` maps only 4 to the YAML the runtime reads
  (`config_sync.py:17-22`). `config set features.mcp_server` (etc.) prints success
  and changes nothing at runtime.
- **`reconfigure` never syncs** — `wizard.reconfigure` saves prefs and skips
  `sync_runtime_prefs_to_yaml` (`wizard.py:370`), so `config reconfigure security`
  is inert at runtime.
- **Four setup paths** (`init`/`onboard`/`install`/`setup`) with `install`
  re-implementing onboarding inline (`main.py:1731-1866`) — most dangerous drift.
- **God-files**: `main.py` is ~4200 lines (47 subparsers + ~40 handlers); `config.py`
  is ~1600 lines / ~65 model classes. Change-amplifiers.
- **`doctor providers` is cosmetic** — prints hardcoded "mock/mock-llm",
  "External providers: disabled" instead of reading `provider_policies`
  (`main.py:2479-2483`).
- **`doctor deep` supersets `verify`** — runs the same `run_all_checks`
  (`doctor/deep.py:287`). Two commands, one output.
- **19 of 47 subcommands are `SUPPRESS`-hidden** — undiscoverable yet callable.

### 4.3 Recommendation (CLI/config)

1. Collapse setup to one engine: `install`/`init` become thin front-ends over
   `OnboardingService.run()`; delete the inline step machine.
2. Fix the config bridge: either expand `RUNTIME_PREF_TO_YAML` to all
   runtime-affecting keys, or reject `config set` of unmapped keys with a clear
   "user-prefs only" warning; add the missing sync to `reconfigure`.
3. Merge `verify` into `doctor` (alias); make `doctor providers` read real policy.
4. Prune the 19 hidden commands (promote or remove); target a ~15-command surface.
5. Split `main.py` and `config.py` into modules.

---

## 5. Plugins / Skills / Personas / Agents

No single extension model — several ad-hoc ones plus dead infrastructure.

- **Three agent-file generators** (`AgentIntegrationGenerator`, `Configurator`,
  `AgentInstaller`) write overlapping content; install flows run two against the
  same files, producing **two different instruction bodies** in one file
  (`agent_manifest.py:152` vs `service.py:467`). Three overlapping `AgentTarget`
  enums (`agent_manifest.py:14`, `agent_installer.py:22`, `boundary.py:21`). **HIGH.**
- **`scope` is ignored** — `Configurator.configure_one(scope=...)` never uses it; a
  `location="global"` agent still writes to the project root → guaranteed
  collision with the generator's output. **HIGH.**
- **No-MCP gap** — `AgentIntegrationGenerator` writes instruction prose telling
  agents to use `opencontext_*` MCP tools **but registers no MCP server**; agents
  configured only via that path get instructions for tools they cannot reach. **HIGH.**
- **Plugin security is not real** — `PluginRegistry.load` does unsandboxed
  `exec_module` with no permission check; the deny-by-default `PluginManifest` model
  is unused; GitHub/URL installs verify a checksum only if one is present
  (`plugin_system.py:982,572`). **HIGH.**
- **Personas are rendered, never consumed** — read only to write files and by the
  `persona` CLI; **zero references in `harness/`, `agents/`, `workflow/`**. They
  influence no execution. **HIGH (product).**
- **Broken health check** — `doctor/component_checks.py:407` imports `SkillRegistry`,
  which does not exist; the check always reports `error`. **HIGH.**
- **Skills**: two formats coexist (v1 `SKILL.md`, v2 `.skill.md`); only v2 is wired,
  but `skill validate` validates v1. `resolver.py`/`compact_rules.py` (skill→task
  matching) are dead — exactly what a phase context pack needs. Agents cannot
  discover skills through any generated artifact. **MED.**
- **Plugin hook bus is inert** — `register_hook`/`trigger_hook` exist but nothing in
  `context/`, `graph/`, `indexing/` triggers a hook. Plugins cannot extend
  analysis. **MED.**

### 5.1 Recommendation (ecosystem)

1. **Collapse agent-file generation to `Configurator` only** (it already does the
   superset: MCP + managed-block instructions + personas + commands + ignore +
   permissions, with safe merge). Delete `AgentIntegrationGenerator`; unify the
   target enum; honor `scope`.
2. **Plugin security**: enforce `PluginManifest` at `load` (validate + gate
   `exec_module` behind the allowlist) or delete the model and stop advertising
   deny-by-default; require checksums.
3. **Skills**: keep v2; delete v1 + dead resolver/compact_rules **or** (higher
   value) wire `resolve_skills`+`generate_compact_rules` into the phase context.
   Fix `skill validate` schema and `doctor/component_checks.py:407`.
4. **Bind personas to the harness** — phase→persona mapping (orchestrator/professor/
   reviewer for plan/explain/verify), inject `persona.system_prompt`; otherwise
   drop two of three.

---

## 6. Cross-cutting code quality

- **Silent failure in the indexing hot loop (HIGH)** — `project_indexer.py:82-99`
  wraps each file (and `rebuild_fts`, `finalize_cross_file_edges`) in
  `except Exception: pass`. A systematically broken parser produces a silently
  incomplete KG — the core deliverable corrupted with no log or error count.
- **~283 broad `except` handlers, ~90 fully silent** (~⅔ don't log). Worst:
  `cli/main.py` (14), `harness/phases.py` (8, zero logger calls), `runner.py` (5),
  `project_indexer.py` (5). Recent commits are converting these — incomplete.
- **Dead module**: `tree_sitter_grammars.py` (a from-scratch grammar git-clone
  installer) has zero references — pip grammar packages won; delete it.
- **`context/observability.py`** — 7 unused methods (export_trace,
  record_quality, show_timeline…); a tracing subsystem largely not wired.
- **Token estimation leaks** — canonical `context/tokenization.py` has 22 importers,
  but 7 inline `len()//4` heuristics bypass it (`bytecode/metrics.py:35`,
  `cache_aligner.py`, `terse.py`).
- **Honest scaffolds** — the 83 "scaffold" mentions are a deliberate honesty
  mechanism (artifacts tagged `_scaffold: True`, status `"planned"`, never
  `"completed"`), not vaporware. Good engineering.
- **Test gaps on live paths** — `learning/` (1606 LOC, 2 test files) and
  `operating_model/` (1658 LOC, **0** dedicated tests) are both on the runtime hot
  path (budget decisions, quality gates). The TTY menu layer remains fragile
  (source of two shipped crashes); a CI guard now exists for raw prompts.

---

## 7. External-project overlap (the "flecos")

| External capability | OC stance | Boundary | Note |
|---|---|---|---|
| Episodic/semantic memory (Engram) | **Depend** (bridge) when present, else local | Cleanest boundary in the repo (`engram_bridge.py`) | But OC keeps a heavier, more-capable local stack; the default wrongly prefers the bridge (§1) |
| Source parsing (tree-sitter) | **Wrap + regex fallback** | Clean degrade | The from-scratch grammar installer is dead — delete |
| External code-edit CLI (aider) | **Depend** (subprocess) | Clean | — |
| Repo map (aider-popularized) | **Reinvent** (`indexing/repo_map.py`) | In-house | Defensible; OC's is contract-shaped |
| Spec→design→tasks pipeline (OpenSpec-like) | **Own** (full in-house SDD) | Internal | Largest reinvent-vs-depend surface; a lot of bespoke orchestration to maintain |
| Vector database (external) | **Reinvent** (`LocalVectorStore`) | In-house, opt-in | Local generator is a PRNG (no real signal); off by default |
| Prompt compression (external lib) | **Reinvent** (AICX/SmartCrusher/terse) | In-house | Strong primitives; the gap is wiring, not capability |
| MCP, rich, InquirerPy, tiktoken | **Depend** (thin wrappers) | Clean | `prompts.py` keeps InquirerPy call sites thin |

**Takeaway**: external boundaries are mostly clean. The two questionable
"reinvent" surfaces are (a) the bespoke SDD orchestration (a lot to maintain for
uncertain advantage over an existing spec framework) and (b) the local
vector/embedding path (currently non-functional — either make it real or lean on
an external vector backend behind the existing `VectorStore` protocol).

---

## 8. Recommendations — prioritized roadmap

### Phase 0 — small, safe, high-impact (do first)
1. **Memory default `auto → local`** (`config.py:602`). Directly fixes the headline
   concern; one line + a test. *(Engram becomes explicit opt-in.)*
2. **Wire the planner**: `runtime.py:766 → RetrievalPlanner.from_config(...,
   memory_store=...)`. Lights up FTS + vector + memory-ranking in one move.
3. **Delete or repair the dead harvest** (`runner.py:502-518`) and log the `except`.
4. **Unify the KG db filename** across explore/runtime/re-index.
5. **Stop the silent index corruption**: log + count per-file failures in
   `project_indexer.py:82`.

### Phase 1 — close the agentic loop
6. **Bridge providers → `LLMGateway`** so real LLM phases work.
7. **artifact → FileEdit → apply** so APPLY writes; scope VERIFY to changed files.
8. **Make gates enforce** (or rename to advisory) in `verify_context`.

### Phase 2 — consolidation (reduce maintenance surface)
9. **One agent-file generator** (`Configurator`); one `AgentTarget` enum; honor `scope`.
10. **One memory store** — collapse `memory_usability` into a rendered projection.
11. **One SDD orchestrator** — retire WorkflowEngine SDD steps + `SDDOrchestrator`.
12. **Config bridge** — map all runtime keys or reject unmapped `config set`.
13. **Collapse setup paths** — `install`/`init` over `OnboardingService`; merge
    `verify` into `doctor`; prune hidden commands.

### Phase 3 — reinforce what exists
14. **Bind personas to harness phases**; wire skills into phase context.
15. **Plugin security** — enforce the manifest allowlist or remove it.
16. **Make local embeddings real** (or lean on an external vector backend) and
    proactive packing-time compression.
17. **Tests** for `learning/`, `operating_model/`, and the TTY menu paths.

---

## Appendix — what is genuinely solid (don't break these)

- Pydantic contracts between layers; the AICX side-channel is correctly
  non-mutating; SmartCrusher/delta are lossless; CCR global state was properly
  removed.
- Real call-graph traversal with unresolved-edge tracking; `ImpactAnalyzer` and the
  git-working-set PageRank personalization are wired and good.
- Fail-closed security: deny-by-default tools, genuine redaction at the sink,
  fail-closed provider policy, air-gapped guards.
- Honest degradation: scaffolds never report as success; "configure a provider"
  warnings surface to the user.
- The Engram bridge itself is a clean, well-bounded external integration — the
  problem is the *default*, not the bridge.
- Navigable-prompt layer (`prompts.py`) with a CI guard against raw prompts.
