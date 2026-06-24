# Code Quality Review — OpenContext Runtime

**Date:** 2026-06-23
**Branch:** `feat/oc-memory-parity-and-polish`
**Lens:** minimalism / anti-over-engineering ("ultra" intensity) + quality-gate & test-gap enforcement
**Status:** REPORT ONLY — no source code was changed.

> Framing note: this report is brand-neutral by request. The two "principle
> sets" it applies are referred to by what they do, not by tool name:
> **(1) code-economy** — the lazy-senior discipline (YAGNI, stdlib before
> custom, native before dependency, one line before fifty, delete over add,
> smallest diff that works); **(2) quality-gate + test-gap** — gate/score a
> change before it is accepted, and detect code that ships without a test.

---

## 0. Method & confidence

- Four independent read-only audits (CLI, harness/agentic core, indexing/retrieval/quality, config/plugins/subsystems) plus two structural maps (the change-execution path, the quality gate).
- Every "unused / dead" claim was produced with a cross-package `grep` for real callers, excluding the defining module, its package `__init__`, and tests.
- The **four boldest whole-subsystem claims were independently re-verified** for this report (`AgentOrchestrator`, `SDDOrchestrator`, `context/observability.py`, `opencontext_providers`, `safety/proxy.py`). Results in Appendix.
- Confidence tags: **HIGH** = grep-clean + spot-verified; **MED** = grep-clean per audit; **VERIFY** = plausible but needs a human check before action (usually a public-API or back-compat surface).

**One caveat that governs the whole of Part A:** most "internally dead" code is
kept green by **(a)** a re-export in `packages/opencontext_core/opencontext_core/__init__.py`
(public API surface) and **(b)** a dedicated test file that exercises the dead
class. "No internal caller" therefore does **not** mean "delete blindly" — each
deletion also means pruning the `__init__` export, removing the pinning test,
and confirming no out-of-tree plugin imports it. That is exactly why this is a
report, not a patch.

---

## 1. Executive summary

| | |
|---|---|
| Non-test source | ~79,500 LOC across 7 packages (310 files in `opencontext_core` alone) |
| High-confidence dead-subsystem surface | **~2,700 LOC** (re-verified) |
| Additional grep-clean deletion/dedup surface | **~1,800 LOC** (MED / VERIFY) |
| Dead/unwired config knobs | **8+** confirmed (`max_fix_loops`, `max_coupling`, `latency`, `token_budgets`, `cache_aligner`, `version`, `auto_index_max_files`, `orchestrator_mode`…) |
| Largest single file | `opencontext_cli/main.py` — 4,220 LOC |
| **Does the agentic system enforce code-economy?** | **No.** It *suggests* it in prompt prose; nothing checks it. The reviewer agent is explicitly told it cannot flag bloat. No gate measures it. |

**The connecting insight.** Part A finds ~4,000+ LOC of dead/duplicated code —
*two complete parallel agent-orchestration spines*, two dead firewall
implementations, an orphaned providers package, a community-detection engine
nothing calls. Part B explains *why it accumulated*: the agentic system that
writes OpenContext's code is told to "keep changes minimal" as advice, but **no
agent is chartered to delete, and no gate rejects bloat.** The dead code is the
evidence that the principle is not enforced. Part C is how you close that loop.

---

# Part A — Code review: what to refactor (keep behavior, cut the excess)

Findings are grouped by type, highest economy first. Every row preserves
behavior. `path:line — what exists → cut/replace — confidence`.

## A1. Dead subsystems — whole-module deletions (the big wins)

These have **zero production callers**. The "reference" keeping them in the
graph is the public `__init__` re-export and/or their own test.

| # | Location | What it is | Action | Conf |
|---|----------|-----------|--------|------|
| 1 | `agents/orchestrator.py` + `agents/base.py` + 5 concrete agents (`code_review_agent.py`, `security_audit_agent.py`, `tdd_enforcer_agent.py`, `mutation_analyst_agent.py`, `context_planner_agent.py`) + `loader.py`, `token_manager.py`, `hooks.py`, `hook_handlers.py`, `memory_manager.py` | A **second, dead agent framework** parallel to the live `harness/` + `agents/executor.py` spine. `AgentOrchestrator` is instantiated only in its own docstring + a test. `AGENT_REGISTRY` has no reader outside `orchestrator.py`. | Delete the framework (~1,100 LOC) | **HIGH** |
| 2 | `agents/sdd_orchestrator.py` **class** `SDDOrchestrator` (lines ~106–349) + its exclusive deps `agents/dag_state.py`, `agents/artifact_store.py`, `agents/result_contract.py` | The pre-fold orchestrator spine. `runner.py` imports only the **module-level tables** `PHASE_DEPENDENCIES` / `WORKFLOW_TRACKS` — never the class. Confirms the documented "folded into `HarnessRunner`" — the old class was left behind. | Delete the class + 3 dep modules; **keep** the two data tables | **HIGH** |
| 3 | `context/observability.py` (578 LOC) — `OtelExporter`, `MetricsCollector`, `ContextDashboard`, `MetricPoint`, `estimate_cost`, `format_*` | Whole module. `runtime.py:1068` only *guards* on `opentelemetry.enabled`; it never builds the exporter. The live `MetricsCollector` is the unrelated `metrics.py:49`. | Delete module + `__init__` re-export | **HIGH** |
| 4 | `safety/proxy.py` (616 LOC) — `SimpleProxyServer`, `ProxyPolicy`, `ContextFirewall` (proxy copy), `_scan_*_simple` | A dead second firewall. The live one is `safety/firewall.py:47` (used 19×). The `_scan_*_simple` fns reimplement `safety/secrets.py` / `safety/scanners.py`. | Delete module + `__init__` re-export | **HIGH** |
| 5 | `packages/opencontext_providers/` (whole package, 120 LOC) | A second `ProviderAdapter` Protocol + mock/registry. **Zero importers** in core or CLI. The live adapters are `opencontext_core/providers/adapters.py`. | Delete package + drop from root `pyproject.toml` | **HIGH** |
| 6 | `adapters/base.py`, `adapters/aider.py`, `adapters/local.py`, `adapters/boundary.py` (~583 LOC) | `AgentAdapter` ABC + Aider/Local/Python adapters + `BoundaryService`. The harness drives agents via `agents/executor` + `llm/sampling_gateway`, not these. Only `verification.py` *imports* them for a health check. `agent_manifest.py` is the lone live file. | Delete the agent-execution subset | MED / VERIFY |
| 7 | `backends/vector/{local,null,semantic}.py` + `backends/protocols.py` `VectorBackend` + `backends/factory.py` `create_vector_backend` | Single-purpose protocol, one factory, **0** prod callers (only a test). The real semantic store is `embeddings/stores.LocalVectorStore`. | Delete the vector half of `backends/` | MED |
| 8 | `indexing/graph_analysis.py` — `detect_communities`, `detect_hubs`, `modularity`, `_betweenness_centrality` (Brandes), `_modularity_label_propagation`, `_canonicalize_labels` (~190 LOC) | Community-detection / betweenness engine. **No** product/CLI/MCP/skill caller — only `test_graph_analysis_advanced.py`. Live half (`compute_centrality`, `detect_god_nodes`, `detect_cycles`, `personalized_pagerank`, `path`, `explain`) stays. | Delete the community/hub half | MED |
| 9 | `harness/engram.py` (212 LOC) — `EngramMemoryAdapter`, `MemoryDelta` | Re-exported by `harness/__init__.py`, consumed by nothing (not even a test). The live `ArchivePhase._build_memory_delta` builds its own dict. | Delete module + re-export | MED |
| 10 | `operating_model/ai_leak.py` — `IndirectPromptInjectionFirewall`, `SourceTrustBoundaryMapper`, `ContextTaintTracker`, `PromptConfigSanitizer`, `UnicodeObfuscationScanner`, `EncodedPayloadDetector` | 6 classes, **0** non-test callers. The rest of `ai_leak.py` (`ReleaseLeakScanner`, `EgressPolicyEngine`, …) IS wired into `main.py` and stays. | Delete the 6 dead classes | MED |
| 11 | `agents/spec_contract.py` (`SpecKernel`, `validate_spec`), `agents/registry.py` (`AgentCapabilities`, `get_agent_capabilities`, `list_supported_agents`), `workflow/harness.py` (`ControlledHarnessPlanner` + 5 types) | Each reachable **only** from its own test. | Delete | MED / VERIFY |

**Subtotal:** items 1–5 are HIGH-confidence and re-verified ≈ **~2,700 LOC**.
Items 6–11 add **~1,800 LOC** behind a VERIFY (mostly: confirm no out-of-tree
plugin / public-API consumer, and remove the pinning tests).

## A2. Dead / unwired configuration

Parsed (and sometimes validated) but **never read** by any formula or code path.
These are pure cognitive load — they imply behavior that does not exist.

| Location | Knob | Note | Conf |
|----------|------|------|------|
| `quality/rules.py:140,382` | `max_fix_loops` | Documents an "in-loop self-correction cap" that **no code enforces**. There is no auto-fix loop. | **HIGH** |
| `quality/rules.py:115,302–313` | `max_coupling` | Parsed + validated A–F; **no reader**. The coupling penalty keys off the hardcoded `COUPLING_KNEE` instead. Its only downstream use (`coupling_grade`) is itself dead (A3). | **HIGH** |
| `config.py:822–830,1207` | `LatencyConfig` / `config.latency` / `max_seconds` | 0 reads. | MED |
| `config.py:813–820,1206` | `WorkflowTokenBudgetConfig` / `config.token_budgets` | 0 reads. | MED |
| `config.py:260–275` + `context/assembler.py:197–210` | `CacheAlignerConfig` + the `CacheAligner.align()` branch | Both `PromptAssembler()` call sites pass no `cache_aligner`, so `_cache_aligner` is always `None` and the branch never runs. | MED |
| `harness/config.py:163–165,251–255` | `active_clients`, `default_client`, `orchestrator_mode` | Parsed from YAML, never read off the config. | MED |
| `harness/config.py:78,216` | `auto_index_max_files` | Docstring claims it caps auto-indexing; no code applies it. | MED |
| `harness/config.py:62,200` | `version` | Parsed, never read. | LOW |

## A3. Duplicated logic — collapse to one

| Location | Duplication | Action | Conf |
|----------|-------------|--------|------|
| `commands/kg_cmd.py:902–1003` | `_generate_ascii_tree` and `_generate_tree_text` are **byte-identical** except 4 connector-glyph strings | One function taking a 4-tuple of connectors (~50 LOC saved) | **HIGH** |
| `main.py:1283–1380` | ~24 `if command == "X": handle_X(args); return` branches, each a 1:1 delegation | A `dict[str, Callable]` dispatch table | **HIGH** |
| `indexing/tree_sitter_parser.py:292–406` | `cyclomatic_complexity` / `function_blocks` / `max_nesting_depth` repeat an identical 9-line parse preamble | Extract `_parse_root(content, language)` | MED |
| `indexing/graph_db.py:332–441` | `insert_node` and `upsert_nodes` spell out the same 14-column `INSERT OR REPLACE` + id derivation | `insert_node` delegates to `upsert_nodes([node])` | MED |
| `indexing/graph_db.py:453–503` | `get_node_by_id` / `get_nodes_by_file` build an identical 12-field `Node(...)` | Extract `_row_to_node(row)` | LOW |
| `indexing/knowledge_graph.py:286,543` | Cross-file edge `INSERT OR IGNORE` SQL duplicated verbatim | One constant + `_insert_cross_edges(conn, edges)` | LOW |
| `harness/checkpoint.py:50` + `configurator/backup.py:55` (+ `configurator/filemerge.py:84`) | `_atomic_write_bytes` duplicated character-for-character | One shared helper | LOW |
| `commands/kg_cmd.py:917–988,1044` | Three copies of the nested tree-walker (ASCII/text/Rich) | One walker yielding `(prefix, connector, name, info)`; callers format | MED |

## A4. Reinvented / over-built — simplify in place

| Location | What exists | Cut/replace | Conf |
|----------|------------|-------------|------|
| `main.py:1070–1141` | Hand-rolled command aliasing poking the private `subparsers._name_parser_map` + a normalizer in `_dispatch` | argparse-native `add_parser(name, aliases=[…])` | MED / VERIFY |
| `commands/bridges_cmd.py:56`, `commands/routes_cmd.py:39` | On no-subcommand, spawn a **whole new `opencontext` process** to print `--help` | `parser.print_help()` (also avoids depending on a possibly-stale on-PATH binary) | MED |
| `indexing/tree_sitter_parser.py:62–94` | `_COMPLEXITY_DECISION_TYPES` / `_FUNCTION_NODE_TYPES` / `_NESTING_TYPES` are `dict[str, frozenset]` with exactly one key (`"python"`) whose value equals the `_DEFAULT_*` fallback | Replace each dict+`.get` with the single `frozenset` | MED |
| `compression/code_compressor.py:480–494` | `_tokenize_line` is dead (its job moved to `tokenize` at line 432) | Delete | **HIGH** |
| `compression/code_compressor.py:469–477` | `_is_local_context` reads `node.parent`, which is never set → always returns `True`; `function_def` param unused | Inline as `True` at the call site | MED / VERIFY |
| `quality/architecture.py:294–309` | `detect_call_cycles` — secondary signal, **0** callers (the live path is `detect_cycles`) | Delete | MED |
| `quality/architecture.py:428–432,930–937` | `coupling_grade` + `_grade_for_degree` + `_COUPLING_BANDS` — A–F grade read by no formula/finding | Delete (this is what made `max_coupling` config dead) | MED |
| `retrieval/scoring.py:42–59` | `RANKING_PRESET_V2_SEMANTIC` — its own comment says "nothing in the runtime references this"; test-only | Delete (or keep explicitly as documented opt-in API) | VERIFY |
| `compression/terse.py:520–776` | Module-level `expand()` / `compress()` / `token_savings()` free wrappers; prod only uses the `TerseCompressor` methods | Drop the free wrappers / the lossy expand round-trip | VERIFY |
| `main.py:690` | `--include-ignored` flag registered on all 3 `tokens` subparsers; `include_ignored` never read | Delete the flag | MED |
| `doctor/component_checks.py:407` | `from …skills.registry import SkillRegistry` — that symbol **does not exist**, so the `try` always hits `except ImportError`; the health sub-check can never pass | Delete the dead sub-check | LOW |
| `tree_sitter_parser.py:903–948` | `_extract_docstring` / `_extract_signature` take a `content` param neither body uses | Drop the param | LOW |

## A5. Load-bearing — do **NOT** cut (false-positive guard)

These look reinvented or redundant but are correctly bespoke / genuinely used.
Listed so a future pass does not "simplify" them by mistake:

- `retrieval/scoring.py` `personalized_pagerank` and `graph_analysis.py` `_tarjan_scc` — hand-rolled **on purpose**; networkx is optional and the pure-Python path is the tested default. **Do not** add networkx.
- `retrieval/planner.py` `select_diverse` (MMR) + `_deduplicate` — every line load-bearing; not stdlib-replaceable.
- `quality/architecture.py` `_compute_duplication` / `_shingles` — bespoke clone detection, live.
- `compression/code_compressor.py` `_python_comment_columns` / `_ast_strip_python_docstrings` — these already *are* the "prefer stdlib" win (use `tokenize`/`ast` over regex). Keep.
- `quality/evaluator.py` `W_*` health weights — the **intentional** hardcoding; not the same thing as the dead `max_coupling`.
- `config.py` `_resolve_flag` / `_coerce_value` bool branch — encode real precedence + `bool("false")` semantics stdlib lacks.
- `profiles/markers.py` (1,603 LOC) — overwhelmingly legitimate **data** (19 profiles + a 219-entry spec table). Not over-engineering.
- `memory/` Protocols (`AgentMemoryStore`, `ProjectMemoryStore`, `EngramClient`) — each has multiple real implementations; legitimate seams.
- `providers/adapters.py` (core), `sdd_profiles.py` builders, `harness/gates.py` dispatch, `mutation/`, `learning/` — all confirmed live.

## A6. Suggested order of attack

1. **Tier 0 (HIGH, biggest LOC, safest):** items A1#1–#5 + A3 `kg_cmd` twins + A4 `_tokenize_line`. ~2,800 LOC gone, behavior identical. Prune the matching `__init__` exports and pinning tests in the same commit.
2. **Tier 1 (config hygiene):** delete A2 dead knobs — or wire `max_fix_loops` into a real loop (see Part C). Cheap, removes phantom-behavior.
3. **Tier 2 (MED/VERIFY):** A1#6–#11, remaining A3/A4 — one module per commit, each gated on a public-API + plugin grep.

---

# Part B — Does the agentic system follow these principles when it changes code?

**Short answer: it is told to, softly, and nothing checks that it did.**

## B1. What exists (advisory prose only)

Minimalism shows up as scattered phrases in agent prompts
(`opencontext_core/personas.py`) and per-phase skill rules:

- OC Builder, `personas.py:274–276`: *"Reuse over reinvention. … keep changes minimal and reversible."*
- OC Architect, `personas.py:247,249`: *"prefer the simplest design that meets the spec." / "Reuse before adding."*
- `skills/builtin/oc-propose-rules:17`: *"Prefer the smallest change that satisfies the task."*
- `skills/templates/oc-apply/SKILL.md:53`: *"Keep each edit minimal and correct; no gold-plating."*
- The single genuine **stdlib-first** line is **stack-detection advice**, not an agent principle: `opencontext_profiles/standards.py:63` *"Prefer pathlib, dataclasses, and the stdlib before adding a dependency."* — rendered into stack docs, not into any agent's system prompt.

## B2. What is missing (the load-bearing gaps)

1. **No "YAGNI / delete dead code / no speculative abstraction / smallest diff"** anywhere in product prompts. The strong forms of the discipline are absent.
2. **The reviewer agent cannot flag bloat.** OC Reviewer (`personas.py:104–153`) is explicitly told to grade *correctness → security → performance → maintainability* and to **"skip pure style."** It has **no charter** to flag over-engineering, single-implementation abstractions, reinvented stdlib, or dead flexibility. The gatekeeper is structurally blind to the entire category of problem Part A found.
3. **No gate enforces code economy.** Gates (`harness/gates.py`) are structural / safety / budget / artifact-existence. The closest thing, `architecture_clean` (`runner.py:986`), only diffs **aggregate** health metrics (duplication, nesting, cycles, god-files) and **defaults to WARNING** — it never asks "did this change add code it didn't need?"
4. **The one quality gate that runs is WARN-by-default.** `architecture_clean` + `quality_standards` run in the standard flow, but emit at most WARNING unless `quality.toml mode="strict"` **and** `BudgetMode.STRICT`. A change does **not** have to pass to be accepted.
5. **Test-gap detection exists but is off the path.** `GraphDatabase.find_test_gaps()` (`indexing/graph_db.py:741`) finds symbols no test references — but it is **CLI-only** (`quality test-gaps`, always exits 0), takes no changed-file scope, and is absent from `QualityMetrics`, the health score, the verify gates, and MCP.
6. **A self-correction loop is advertised but does not exist.** `max_fix_loops` is dead config; `runner.py:1093`'s "fed to the Builder for the in-loop fix" is aspirational — no code feeds findings back.

## B3. Verdict

Code-economy in the change path is **suggested to the writer, never checked at
the gate.** The reviewer is forbidden from raising it; no metric scores it; the
one gate that could is non-blocking by default. This is precisely the
configuration under which Part A's dead code accumulates: a Builder can add a
whole parallel orchestrator, a second firewall, an unused providers package —
and every automated check stays green.

---

# Part C — Baking the principles in (code-economy + quality-gate + test-gap)

The goal: make the two principle sets **enforced**, not advisory, so the agentic
system produces lean, tested code by construction. Ordered by leverage.

## C1. Give the reviewer a code-economy charter — *highest leverage, lowest cost*

Add a review axis to OC Reviewer (`personas.py:104–153`): flag
**over-engineering, single-implementation abstractions, reinvented stdlib, dead
flexibility, and code added without a clear need.** Today it is told the
opposite ("skip style"). This one prompt change turns the gatekeeper from blind
to sighted on the entire Part-A category. (OpenContext's standalone
`review_cmd.py:83` already knows the phrase "over-engineering, or missing
abstractions" — lift that into the *agent* path.)

## C2. Make the writer's economy explicit

In OC Builder (`personas.py:254–281`), promote the soft "keep changes minimal"
into the explicit ladder, stated as rules the Reviewer will check:
*does this need to exist? → stdlib before custom → native before dependency →
one line before fifty → delete dead code you touch → smallest diff that works.*
Strengthen `oc-design-rules` "justify every new component" into an explicit
"no new abstraction without a second caller today" rule.

## C3. Enforce, don't suggest — three gate changes

1. **Promote the existing quality gate to block-by-default in the agentic flow.**
   `architecture_clean` / `quality_standards` already run; make a *regression* in
   the health score a FAILED (not WARNING) status inside the harness, independent
   of `BudgetMode`. Keep WARN as the opt-down, not the default.
2. **Wire test-gaps into the gate (the net-new capability worth keeping).**
   Scope `find_test_gaps()` to *changed* symbols, add a `test_gaps` signal to
   `QualityMetrics` (`models.py:62`) with a penalty term in `compute_health`
   (`evaluator.py:204`), surface it as `Finding(category="tests")` (the enum
   already reserves `'tests'`), and dispatch it as a verify-phase gate beside
   `architecture_clean`. This is "a function shipped without a test fails the
   gate" — the single highest-value addition for code quality.
3. **Add a code-economy signal.** Extend `architecture_clean` (or add a gate) to
   flag **net-new abstraction / LOC disproportionate to the task** — e.g. a new
   ABC/Protocol/factory with one implementation, or a new module no new caller
   imports. Pair it with the reviewer charter from C1 so the finding has both a
   deterministic sensor and a judgment check.

## C4. Make the self-correction loop real (ties it all together)

`max_fix_loops` is dead config promising a loop that doesn't exist. Build the
loop it names:

```
apply (Builder)
  └─> verify gate: quality regression? test-gap on changed symbols? over-engineering finding?
        ├─ pass ──────────────────────────────> accept
        └─ fail ─> feed findings back to Builder ─> re-apply  (bounded by max_fix_loops)
```

This is the synthesis: **the writer is told to be lean (C1/C2), the gate checks
that it was — economy + quality + test coverage (C3) — and the loop sends
failures back to be fixed (C4), bounded by the config knob that already exists.**
Three principle sets, one enforced loop, instead of three sets of advice nobody
verifies.

## C5. Recommendation summary

| # | Change | File(s) | Effort | Leverage |
|---|--------|---------|--------|----------|
| C1 | Reviewer gains over-engineering charter | `personas.py:104–153` | XS | ★★★★★ |
| C2 | Builder gains explicit economy ladder | `personas.py:254–281`, `oc-design-rules` | XS | ★★★★ |
| C3.1 | Quality gate blocks by default in flow | `harness/runner.py:564–580`, `evaluator._status` | S | ★★★★ |
| C3.2 | Test-gaps as a scored, gating signal | `quality/models.py`, `evaluator.py`, `runner.py`, `graph_db.py:741` | M | ★★★★★ |
| C3.3 | Code-economy / net-new-abstraction signal | `harness/runner.py:986`, `quality/architecture.py` | M | ★★★ |
| C4 | Real apply→gate→fix loop | `runner.py`, consume `max_fix_loops` | M | ★★★★ |

---

# Part D — Absorbing review disciplines into the process (max architecture, min effort)

**Thesis: you already own the lenses. The economic move is to *promote and wire
what exists*, not to *build a review framework*.** OpenContext already contains
~7 review disciplines as phases/gates. Most are opt-in, non-blocking, or
CLI-only. The highest ROI is turning them on and pointing them at the right
scope — net-new construction is small.

## D1. Inventory — review lenses OpenContext already has

| Lens / discipline | Where it lives | Status today | Gap |
|---|---|---|---|
| Architecture health (cycles, god-files, duplication, nesting, complexity) | `VerifyPhase` `phases.py:1819` → `architecture_clean`+`quality_standards` gates `runner.py:986,1084` | Runs in default flow but **WARN-by-default** | Make it block; default posture |
| Code review (correctness/security/perf/maintainability) | `ReviewPhase` `phases.py:2028`, OC Reviewer `personas.py:104-153` | Runs, but reviewer is told to **"skip style"** → blind to bloat | No economy charter |
| Adversarial dual review | `JudgmentDayPhase` `phases.py:2169` | **Opt-in** (`full+judgment`, `runner.py:349`) | Not risk-gated into default |
| Line/pattern rules (max LOC, forbidden patterns) | `GGARulesPhase` `phases.py:2311` | **Opt-in** (`full+gga`) — and is a BLOCKER when on | Cheap to default-on |
| Mutation testing | `mutation/runner.py` | Present; opt-in track | Not wired to the gate verdict |
| Security / privacy / secret-leak / egress | Gates `gates.py:81,296,379,502` | Wired as gates | Strongest existing lens — keep |
| Strict-TDD (failing test must exist) | `FailingTestExistsGate` `gates.py:544` | The one true **block** guardrail | Model for the rest |
| Test-gap (symbol has no test) | `find_test_gaps()` `graph_db.py:741` | **CLI-only, exit-0** | Not a metric, not a gate |
| Code-economy / YAGNI / dead-code | — | **Absent** | The Part-A category nobody checks |

**Takeaway:** of the disciplines worth enforcing, only **two are genuinely
missing** (code-economy, and a wired test-gap signal). The other five exist —
they are just dialed to *advisory* or *opt-in*.

## D2. The five insertion points (the substrate — already built)

A new or promoted lens plugs into one of five places. Cheapest → most effort;
advisory → enforced. **No new abstraction is needed — these all exist.**

| # | Insertion point | Mechanism | Cost to add a lens | Enforced? |
|---|---|---|---|---|
| 1 | **Persona charter** | a line in `personas.py` (Builder/Reviewer) | XS (prose) | No (advice) |
| 2 | **Builtin skill-rules** | a `SKILL.md` under `skills/builtin/<phase>-rules/`, injected by `_phase_skill_rules()` `phases.py:936` | XS (prose) | No (advice) |
| 3 | **Deterministic gate** | a `*Gate` class in `gates.py` + declare in `config.py` PhaseConfig + `_eval_*` in `runner.py` | S–M (code) | **Yes** |
| 4 | **MCP tool** | register beside `opencontext_quality` `mcp_stdio.py:479` | S | On-demand |
| 5 | **CLI / CI** | a subcommand + `ci-check` | S | Manual/CI |

**Concrete gap in the substrate:** builtin skill-rules exist for
`propose/spec/design/tasks` only — **`apply` and `review` have no rules dir.**
That is exactly where code is *written* and *judged*. Adding
`skills/builtin/oc-apply-rules/` (economy ladder) and
`skills/builtin/oc-review-rules/` (lens checklist) is two prose files into a
mechanism that already loads them. No code.

## D3. "Other systems like this one" — disciplines worth absorbing, and the verdict

Each external discipline maps to an OpenContext capability. The decision is
**reuse / promote / wire / skip** — almost never "build".

| Discipline (what it enforces) | OC already has | Verdict | Effort |
|---|---|---|---|
| **Code-economy / minimalism** (YAGNI, stdlib-first, delete-over-add, smallest diff) | nothing | **Build (small):** reviewer charter + economy sensor reusing the graph | XS prompt + M sensor |
| **Test-gap / quality-gate** (no untested changed code) | `find_test_gaps()` (CLI-only) | **Wire:** make it a scored gate on changed scope | M |
| **Adversarial dual-review** (two blind reviewers, then re-judge) | `JudgmentDayPhase` (opt-in) | **Promote, risk-gated:** auto-on for high-risk diffs only | XS |
| **Multi-model second opinion** (a different model reviews) | LLM gateway / sampling | **Skip-by-default, opt-in:** expensive; reserve for high-risk | XS (flag) |
| **Token / context economy** (compress agent↔agent handoffs) | `compression/terse.py` `TerseCompressor` | **Wire:** compress phase handoffs → offsets enforcement token cost | S |
| **Dependency hygiene** (no new dep for a few lines) | stack standards `standards.py:63` (docs only) | **Promote:** into Builder charter + an economy-sensor check | XS |
| **Knowledge-graph grounding** | the whole KG | already core | — |
| **Persistent memory** (carry decisions across runs) | memory subsystem | already core | — |

**Key economic point:** absorbing the *token-economy* discipline (compress
handoffs via the `TerseCompressor` you already ship) can make the whole
enforcement layer **token-neutral or token-negative** — the prompt tokens spent
on charters/rules are offset by the tokens saved on compressed inter-phase
context. Enforcement does not have to cost; designed right, it pays for itself.

## D4. The lazy target architecture — one pass, one table, the existing loop

Do **not** build a lens-plugin SDK. Model every lens as a row in a single
table, where each lens is at most three cheap parts, all feeding the **same
apply→gate→fix loop from Part C4**:

```
lens = {
  sensor:  optional deterministic check (free; reuse graph_db / architecture.py / find_test_gaps),
  charter: one line in a persona or <phase>-rules SKILL.md (advice to the writer),
  gate:    one verdict in the verify phase (the enforcement point),
  when:    always | changed-scope | high-risk-only | opt-in   # sequencing = cost control
}
```

Sequencing IS the cost control:
- **`always`** — deterministic sensors (architecture health, test-gap, economy/dead-symbol). Near-free; run every change.
- **`changed-scope`** — model-judgment lenses (reviewer economy + correctness) scoped to the diff, not the repo.
- **`high-risk-only`** — adversarial dual-review, auto-triggered by blast-radius (`opencontext_impact`) or touched security paths.
- **`opt-in`** — multi-model second opinion. Costs the most; never default.

This is one `lenses` table + the loop you already need for `max_fix_loops`. No
registry, no SDK, no new orchestrator.

## D5. Economics — ROI model and ranking

Two cost ledgers:

- **Avoided cost (the gain):** dead code, bugs, and rework prevented. **Part A
  is the worked proof** — ~4,500 LOC of dead/duplicated code that an enforced
  economy loop would have blocked at write time, plus the test upkeep, review
  time, and cognitive load that code now imposes forever.
- **Enforcement cost (the spend):** charter/rule prose ≈ hundreds of prompt
  tokens/phase; deterministic gates ≈ free compute; model-judgment lenses cost
  one scoped call; multi-model/adversarial cost N calls (hence opt-in). Handoff
  compression (D3) offsets the prompt-token spend.

**ROI = (defects caught × cost-per-defect) ÷ (tokens + build effort).** Ranking:

| Tier | Lens | Why this tier |
|---|---|---|
| **Do first** (cheap, high-catch) | reviewer economy charter; flip architecture gate to block; wire test-gap sensor; add the 2 missing rules dirs | XS–M effort, deterministic or prose, catches the Part-A category |
| **Do next** (cheap, reuse) | economy/dead-symbol sensor (reuse `graph_db` reachability + `architecture.py`); handoff compression | M, pure reuse, token-positive |
| **Risk-gate** (costs per use) | promote adversarial dual-review for high-risk diffs only | XS to wire, bounded by trigger |
| **Opt-in only** (expensive) | multi-model second opinion; full mutation runs | reserve for release/high-risk |

## D6. Phased rollout — minimum effort first

| Phase | Scope | Files | New code? | ROI |
|---|---|---|---|---|
| **0** | Reviewer economy charter (C1) + Builder economy ladder (C2) + add `oc-apply-rules`/`oc-review-rules` SKILL.md | `personas.py`, `skills/builtin/*` | **~none** (prose) | ★★★★★ |
| **1** | Flip `architecture_clean`/`quality_standards` to block-by-default in the harness; promote `full+gga` line/pattern rules into default | `runner.py:564-580`, `evaluator._status`, track config | XS | ★★★★ |
| **2** | Wire test-gap as a scored, gating signal on changed scope | `graph_db.py:741`, `quality/models.py:62`, `evaluator.py:204`, `runner.py` | M (reuse) | ★★★★★ |
| **3** | Economy/dead-symbol sensor (flag net-new abstraction + unused-on-changed-scope) | new `*Gate`, reuse `architecture.py` + graph reachability | M | ★★★ |
| **4** | Build the real apply→gate→fix loop consuming `max_fix_loops`; compress handoffs via `TerseCompressor` | `runner.py`, `compression/terse.py` | M | ★★★★ |
| **5** | Risk-gate adversarial dual-review (auto-on by blast radius); keep multi-model opt-in | `runner.py` trigger, `opencontext_impact` | XS | ★★ |

Each phase ships independently and is reversible. Phase 0 alone closes the
single biggest gap (the reviewer can finally see bloat) at ~zero code.

## D7. Anti-scope — what NOT to build (the lazy guardrail)

- **No lens-plugin SDK / DSL.** A `lenses` table + the existing gate/persona/rule
  mechanisms cover every case. A plugin framework is the exact over-engineering
  this report exists to prevent.
- **No new orchestrator.** Everything hangs off `HarnessRunner` + `VerifyPhase`.
- **No multi-model-by-default.** It is the most expensive lens for the least
  marginal catch on routine diffs; opt-in only.
- **No per-lens config explosion.** One enable/disable + one `when` per lens.
  Avoid recreating the dead-config problem from Part A2.
- **Don't rebuild what's opt-in.** `JudgmentDayPhase`, `GGARulesPhase`, mutation,
  and the security gates already exist — promote, don't reimplement.

---

# Part E — Phase-by-phase implementation plan (detailed)

Plan only — nothing here is built. Each phase ships independently, is reversible,
and is scoped to changed files (never the whole legacy repo). Effort: XS = prose,
S = a few edits, M = a new gate/loop. The non-obvious traps found while verifying
the insertion points are called out per phase under **Gotchas** — those are what
make or break each phase.

## E0. The concrete lens table (pins the architecture)

Every lens is at most: a deterministic **sensor** (free), a one-line **charter**
(advice to the writer/reviewer), a **gate** (the enforcement verdict), and a
**`when`** (cost control). All feed the one apply→gate→fix loop.

| Lens | Sensor (deterministic) | Charter | Gate | `when` | Phase |
|---|---|---|---|---|---|
| Architecture health | `evaluator.snapshot` (exists) | design-rules (exists) | `architecture_clean` (exists) | always | 1 |
| Language standards | `evaluator.evaluate` (exists) | — | `quality_standards` (exists) | changed-scope | 1 |
| Test-gap | `find_test_gaps(changed)` (extend) | tester charter (exists) | `tests_covered` (new) | always | 2 |
| Code-economy | unused-new-symbol + single-impl (new, graph) | reviewer+builder charter (new) | `code_economy` (new) | always | 3 |
| Line/pattern (GGA) | `GGARulesPhase` (exists) | — | gga blocker (exists) | opt-in→default | 1 |
| Adversarial dual-review | — | reviewer charter (exists) | `JudgmentDayPhase` (exists) | high-risk-only | 5 |
| Multi-model second opinion | — | — | LLM gateway | opt-in only | 5 |
| Token economy | `TerseCompressor` (exists) | — | (handoff compression, not a gate) | always | 4 |

**Dependency order:** 0 and 1 are independent and come first. 2 and 3 are
sensors that *block* only once 1's policy exists. 4 (the fix loop) needs the
gates from 1–3 to have something to feed back. 5 is independent, best last.

```
0 (charters) ─┐
              ├─> 2 (test-gap) ─┐
1 (block) ────┤                 ├─> 4 (fix loop + compression) ─> 5 (risk-gated review)
              └─> 3 (economy) ──┘
```

---

## E1 — Phase 0: charters + the two missing rules dirs  ·  XS  ·  ROI ★★★★★

**Closes:** the reviewer is blind to bloat; apply/review get no injected rules.

**Edits (described, not coded):**
1. **Reviewer economy axis** — `personas.py:117-118`. After "…then performance,
   then maintainability" add a fourth axis: *"then economy — flag
   over-engineering, reinvented stdlib, single-implementation abstractions,
   dead/unused code, and a dependency a few lines would replace."* Add one
   Principles bullet (`:146`): *"A change that adds code it does not need is a
   finding, even if correct."*
2. **Builder economy ladder** — `personas.py:274-275`. After "Reuse over
   reinvention" add: *"Climb the ladder before adding code: does it need to
   exist? → stdlib/native before a dependency → an existing symbol before a new
   one → one line before fifty. Delete dead code you touch. No new abstraction
   without a second caller today."*
3. **Two builtin rules dirs** — create `skills/builtin/oc-apply-rules/SKILL.md`
   and `skills/builtin/oc-review-rules/SKILL.md`, same format as
   `oc-design-rules/SKILL.md`. Frontmatter `trigger:` is the binding key —
   `trigger: apply, implement, code` and `trigger: review, code review` — matched
   by `_score_task_context` against `task_type=phase`.

**Gotcha (the one that decides "zero code"):** `run_phase_executor(state, phase)`
calls `_phase_skill_rules(phase)` generically (`phases.py:1024`), so any phase
routing through it picks up the new dirs for free. **But `ApplyPhase` writes via
its own `CodeEditExecutor` (`phases.py:1143`)** — verify it routes through
`run_phase_executor`; if not, add the one line `_phase_skill_rules("apply")` to
the apply executor's context assembly. Review phase routes through the generic
path. So: ~zero code, plus at most one line for apply.

**Acceptance:** a change that adds a one-implementation wrapper → Reviewer emits
an `economy` finding; the `## Applicable skills` block appears in the apply and
review executor context (assert via a harness test that inspects the rendered
context).

**Risk/rollback:** prose only; revert the persona strings / delete two files.

---

## E2 — Phase 1: block-by-default gate policy  ·  S  ·  ROI ★★★★

**Closes:** the quality gate runs but only WARNs unless two STRICT switches are
both on, so a regressing change is still accepted.

**Mechanism found:** blocking needs *both* `BudgetMode.STRICT` (run loop,
`runner.py:569-573`) *and* `QualityMode.STRICT` (`evaluator._status:482`, which
otherwise returns WARNING; `_eval_architecture_gate:1056` only returns FAILED on
error/critical severity). Default `QualityMode` is `RATCHET` (`rules.py:141`).

**Edits:**
1. Add one harness knob `gate_policy: block | warn` (default `block`) to
   `harness/config.py`. **Do not** touch `QualityMode` / `BudgetMode` semantics —
   keep the policy at the run-loop level only.
2. `runner.py:569-582` — under `gate_policy == "block"`, a verify-phase gate
   whose status is FAILED **or** WARNING-due-to-regression escalates
   `final_status = FAILED` (and breaks), independent of `BudgetMode`. `warn` =
   today's behavior (the opt-down).
3. (Optional) promote `full+gga` line/pattern rules into the default `full`
   track — or defer, since the Phase-3 `code_economy` gate covers the same
   ground deterministically without needing `.opencontext/rules.yaml`.

**Gotcha:** gates legitimately **SKIP** on no-git-diff / stale-graph
(`runner.py:1011,1024`). The block policy must escalate only PASSED/FAILED/WARNING
— **never turn SKIPPED into FAILED**, or every non-git or unindexed run hard-fails.

**Acceptance:** a change that adds a clone (health regresses) → run status FAILED
in default mode; the same change under `gate_policy: warn` → WARNING; a
no-git-diff run → still SKIPPED (not FAILED).

**Risk/rollback:** false blocks on messy repos → mitigated (gates are
changed-scope) and escaped via `gate_policy: warn`. Rollback = flip the knob.

---

## E3 — Phase 2: test-gap as a scored, gating signal  ·  M (reuse)  ·  ROI ★★★★★

**Closes:** "a function shipped without a test" is detectable (`find_test_gaps`)
but CLI-only, exit-0, repo-wide — never gates a change.

**Edits (all reuse of existing machinery):**
1. `graph_db.py:741` — add `changed_files: set[str] | None = None`; when given,
   keep only rows whose `file_path` is in scope. The covered/uncovered logic is
   unchanged.
2. `quality/models.py:62` — add `test_gaps: int = 0` to `QualityMetrics`.
   **Must also** add it to `as_dict` (`:86`) and `from_dict` (`:104`) — the
   struct's contract is lossless JSON round-trip; a field that skips those breaks
   the baseline diff.
3. `evaluator.py` — add module constants `W_TEST_GAP` + `_CAP_TEST_GAP` (near
   `:73`/`:91`) and a `"test_gaps"` term in `compute_health` (`:204`). Populate
   `metrics.test_gaps` in the `snapshot(changed_files=…)` path from
   `find_test_gaps(changed_files=changed)` — **count only changed/new symbols**,
   else the legacy untested repo tanks every score.
4. Emit one `Finding(category="tests", …)` per gap (the enum already lists
   `'tests'`, `models.py:47`).
5. New gate `tests_covered` — declare in the `verify` `PhaseConfig.gates`
   (`config.py:135-145`) and add `_eval_test_gaps_gate(state, result)` in
   `runner.py` beside `:986`/`:1084`, scoped via `_git_changed_files`, same SKIP
   semantics as the sibling gates. With Phase 1's `block` policy, a new untested
   function in the diff blocks.

**Gotcha:** this is a **structural proxy** (does any test *reference* the symbol),
not execution/line coverage — name it honestly in the finding so it is not
mistaken for real coverage. Scope strictly to changed/new symbols.

**Acceptance:** add a new public function with no referencing test → `tests_covered`
FAILED; add a test that calls it → PASSED; pre-existing untested code in
unchanged files → does not fire.

**Risk/rollback:** noisy on test-helper patterns → `is_test_path` already excludes
test files; rollback = drop the gate from the verify list (knob), code stays inert.

**Depends:** Phase 1 to *block*; works as a sensor/WARNING without it.

---

## E4 — Phase 3: code-economy sensor  ·  M  ·  ROI ★★★

**Closes:** the entire Part-A category (dead/speculative code) has no automated
sensor — only the new reviewer charter, which is judgment, not deterministic.

**Edits — reuse the `find_test_gaps` graph pattern (inverted):**
1. **Signal A — unused new symbol:** a symbol defined in a *changed* file with
   **zero inbound edges excluding test files**. This is exactly the Part-A shape
   (an `AgentOrchestrator` nobody calls). Same SQL shape as `find_test_gaps`,
   inverted (no non-test inbound edge).
2. **Signal B — single-implementation abstraction:** a *new* class marked
   abstract (ABC/Protocol/base) with ≤1 implementor in the graph.
3. **Signal C — net-new LOC vs task size (advisory only):** added LOC
   disproportionate to the task; low confidence → WARNING/info, never blocks.
4. Add `unused_symbols: int` to `QualityMetrics` (+ `as_dict`/`from_dict`), a
   penalty term in `compute_health`, `Finding(category="architecture")`, and a
   `code_economy` gate in the verify list — mirrors Phase 2 exactly.

**Gotcha (critical — this is the Part-A governing caveat in code form):** a
symbol re-exported in a package `__init__.py` is *public API*, not dead. The
sensor **must exclude symbols re-exported from `__init__`** or it will flag every
intentional public export. Restrict to *newly added* symbols (changed scope), not
the legacy graph.

**Acceptance:** re-run against the Part-A dead code → Signal A flags the
unreferenced new symbols; a new symbol that a new caller references → not flagged;
a new public export listed in `__init__` → not flagged.

**Risk/rollback:** over-flagging public API → the `__init__` exclusion above;
rollback = drop the gate. Pairs with the Phase-0 reviewer charter (sensor +
judgment cover each other's blind spots).

**Depends:** Phase 1 (block); shares the metric/gate scaffolding with Phase 2.

---

## E5 — Phase 4: the real apply→gate→fix loop + handoff compression  ·  M  ·  ROI ★★★★

**Closes:** `max_fix_loops` is dead config (`rules.py:140`, default 2) — it
promises in-loop self-correction that does not exist. This phase builds it and
makes enforcement pay for itself in tokens.

**Edits:**
1. **The loop** — in the run loop (`runner.py`), wrap the apply→verify segment.
   On a blocking verify verdict with `loops_remaining > 0`: feed the structured
   gate findings (already emitted as `metadata.new_findings` / `findings` at
   `runner.py:1071,1137`) back into the apply executor context as a
   "fix-these-findings" block, re-run apply→verify, decrement. Consume
   `rules.max_fix_loops` — the dead knob goes live. After the cap, surface FAILED
   (do not spin).
2. **Handoff compression** — `run_phase_executor` builds `base_context =
   prior_artifact + pack` (`phases.py:1020`). Route the large handoff fields
   through `TerseCompressor.compress()` (`compression/terse.py`) above a size
   threshold. The tokens saved on compressed handoffs offset the prose added in
   Phase 0 — net the enforcement layer can be **token-neutral or negative**.

**Gotcha:** `TerseCompressor` is **lossy** (its own docstring). Compress **only
the handoff context** (prior artifacts, the pack) — **never** the task statement
or the code being edited, and only above a token threshold (small handoffs cost
more to compress than they save). The loop must be hard-bounded by
`max_fix_loops`; a non-converging change exits FAILED, it does not loop forever.

**Acceptance:** a change that fails verify once is auto-fixed within
`max_fix_loops` with no human; a change that cannot be fixed exits FAILED at the
cap; measured handoff tokens drop vs the pre-compression baseline;
`max_fix_loops: 0` disables the loop (rollback knob).

**Depends:** Phases 1–3 (the gates whose findings the loop feeds back).

---

## E6 — Phase 5: risk-gated adversarial review + opt-in multi-model  ·  XS–S  ·  ROI ★★

**Closes:** the strongest review lens (`JudgmentDayPhase`, `phases.py:2169`) is
opt-in (`full+judgment`, `runner.py:349`) — never auto-applied where it matters,
and the most expensive lenses risk negating the economic gain if run by default.

**Edits:**
1. **Auto-trigger by risk** — after apply, compute blast radius from the graph
   (reuse `opencontext_impact` / changed-symbol in-degree); if impact ≥ a
   threshold **or** a security/safety path is touched (reuse the security gates'
   path matching), inject `JudgmentDayPhase` into this run's schedule only. Low-
   impact diffs skip it. This is the `when: high-risk-only` row.
2. **Multi-model second opinion** — keep behind an explicit flag
   (`--second-opinion` / config), routed via the LLM gateway with a different
   model. **Never default** — it is the highest-cost / lowest-marginal-catch lens
   on routine diffs.

**Gotcha:** adversarial review costs N model calls — the trigger MUST be
selective or it erases the savings. Tie it to blast radius / risk, not to every
run.

**Acceptance:** a 1-line low-impact change does **not** trigger judgment; a change
touching a high-in-degree symbol or a `safety/`/`security/` path **does**;
multi-model stays off unless the flag is set.

**Risk/rollback:** cost creep → the selective trigger + opt-in flag; rollback =
disable the trigger (back to opt-in track only).

**Depends:** none structurally; best sequenced last so it judges a diff the
cheaper lenses already cleaned.

---

## E7 — Definition of done (per phase) and what stays out

**Done = each of:** (a) the gate/charter is live on the default `full` flow;
(b) one harness test asserts the observable in *Acceptance*; (c) the behavior is
behind a knob with a documented rollback; (d) it is scoped to changed files.

**Stays out (re-stating D7 as hard constraints for this plan):** no lens-plugin
SDK, no new orchestrator, no per-lens config beyond enable + `when`, no
multi-model-by-default. Every phase reuses `HarnessRunner` + `VerifyPhase` +
`QualityEvaluator` + the gate/persona/skill-rules mechanisms that already exist.
The plan adds **2 prose files, ~4 new metric fields, 3 new gates, 1 loop, 1
trigger** — and deletes 1 dead config knob by making it live. That is the whole
surface.

---

## Appendix — re-verification log (claims I checked myself)

```
AgentOrchestrator(  → only orchestrator.py docstring + agents/__init__.py docstring   (no prod caller)
AGENT_REGISTRY      → readers only inside orchestrator.py itself                       (registry, no reader)
SDDOrchestrator(    → 0 instantiations outside tests                                   (class dead; tables live)
OtelExporter/ContextDashboard → only opencontext_core/__init__.py re-export           (module dead)
opencontext_providers → 0 importers in opencontext_core + opencontext_cli             (package orphaned)
SimpleProxyServer/ProxyPolicy → only opencontext_core/__init__.py re-export           (module dead)
```

**Governing caveat (repeat):** the dead symbols above are still listed in
`opencontext_core/__init__.py`'s public API and pinned by dedicated tests.
Deleting them is safe *internally*; before acting, prune the `__init__` exports,
remove the pinning tests, and confirm no out-of-tree plugin imports the public
names. Nothing in this report has been applied.
