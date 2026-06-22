# Architecture & Code-Quality Enforcement — Planning Document

Status: **Phases 1+2 shipped** (commit `8bb314c`). Live surfaces: the `quality/` engine
(models/rules/architecture[Tarjan SCC + centrality + tree-sitter complexity]/languages/
baseline/evaluator), the `opencontext quality check|gate` CLI, the `opencontext_quality`
MCP tool, the harness gate (health snapshot at explore, re-check after apply), and
`opencontext ci-check run` (folds in the architecture/quality findings). **Phase 3
remains** (deferred): duplication/depth metrics, a single rolled-up score, per-persona
wiring (Architect during design, Reviewer during verify), evolution tracking across runs,
and wiring the currently-unwired learned task-pattern → retrieval boost
(`PatternLearner.suggest_context_boost`, scaffolding today). Owner: TBD.

## Goal

Give the SDD loop a **continuous architecture-quality sense**: as the agent works, the
harness measures the project's architecture and per-language code health, and when a change
would **degrade** it, the loop catches that **inside the same run** and the agent
self-corrects — automatically, before the change is accepted.

It must feel like a built-in sensor, not a chore: **zero configuration to start, invisible
until it matters.** The user is never asked to author rules, wire CI, or run a command for
the default behavior to work. Forcing happens *in the agent loop*; the human is only
involved if the agent cannot fix the regression itself.

### Non-goals

- Not a config exercise — the default path needs **zero setup** (no rules file required).
- Not primarily a CLI/CI chore the user runs — it lives **in the agentic loop**; CLI/CI are
  optional surfaces on the same engine.
- Not aesthetic or subjective "perfect design" — it senses the **measurable**.
- Not a replacement for each language's linters/type-checkers — it **orchestrates** them.
- Not an external service or binary dependency — native and client-side.

## Default experience (zero-config, in-loop)

This is the whole point — what happens with **no config at all**:

1. **Session snapshot.** At run start (`explore`) the harness records an architecture
   **health baseline** from the knowledge graph it already builds — a single score plus the
   built-in signals (cycles, god-files, coupling). No rules file needed.
2. **Agent works** through the normal SDD phases.
3. **Session re-check.** After `apply`, the harness recomputes health on the changed scope
   and **diffs against the snapshot**. Built-in regression rules (no *new* cycles, no *new*
   god-file, no *new* boundary break, health score not dropping) apply automatically.
4. **Self-correction in the loop.** If the change degraded architecture, the finding is fed
   back to the agent (Builder/Reviewer persona) and it fixes it **in the same run** — like
   the existing test/verify feedback. The user sees nothing unless asked.
5. **One-line summary.** The run reports a compact health delta (e.g. `architecture
   9120 → 9180 ▲`); only a regression the agent could not resolve is surfaced to the user.

The only config most users ever touch is two keys: **`enabled`** (turn the whole
architecture feature on/off) and **`max_fix_loops`** (cap the in-loop self-correction
attempts so it never burns tokens). Both have sensible defaults — on, and a small loop cap —
so even those are optional.

Everything else below — explicit rules, layers/boundaries, CLI, CI, strictness — is an
**optional refinement** layered on this default. The sensor works out of the box; teams opt
into hard standards only when they want them.

## Principles

- **Zero-config by default.** Sensible built-in signals + regression detection with no
  rules file. Configuration only *tightens* behavior; it is never required.
- **In the loop, low-friction.** The harness runs it automatically and the agent
  self-corrects; the user is not asked to invoke anything for the default behavior.
- **Native + deterministic.** Runs off the knowledge graph and existing tools; no new
  dependency, no model in the sense/check path.
- **Regression-first (ratchet by default).** Block what this change made *worse*; never
  block on pre-existing debt. Hard absolute thresholds are opt-in.
- **Degrade honestly.** Never report "clean" for a check that did not actually run; a
  missing optional language tool is reported, not silently passed.
- **Optional surfaces, one engine.** The same engine also powers an optional CLI/CI gate for
  teams that want a manual or merge-time check — but that is additive, not the default.

## What it enforces

### Architecture (cross-language, from the knowledge graph)

Computed from the existing `dependency_graph` + `call_graph` + `graph_analysis`:

| Rule | Meaning | Source signal |
|------|---------|---------------|
| `max_cycles` | No new import/call cycles | strongly-connected components (Tarjan) over the dependency graph |
| `no_god_files` | No file/symbol with excessive fan-in or size | `graph_analysis` centrality (in-degree / fan-in) + LOC |
| `layers` / `boundaries` | Declared layers may only depend in the allowed direction | path-matched edges in the dependency graph |
| `max_coupling` | Cap on fan-in/fan-out per module | `graph_analysis` degrees |
| `max_complexity` (`max_cc`) | Cyclomatic complexity per symbol | tree-sitter AST (branch/loop counting) |
| `max_depth` | Directory / nesting depth ceiling | path analysis |

### Per-language code quality (delegated to each language's tools)

We already detect the project's stack (technology profiles) and each profile already
declares its canonical `validation_commands` (e.g. Python → `ruff` / `mypy` / `pytest`;
Node → lint/test; PHP → `phpstan` / `phpcs` / `pint`). The enforcement system:

1. Detects the languages touched by the change (profiles + changed files).
2. Runs the matching language tools (lint, type-check, format-check, test) over the
   changed scope.
3. Normalizes each tool's output into a common finding model (file, line, rule, severity).
4. Applies the configured thresholds and verdict.

A small **language → standards** registry maps each language to its tool set and a
**standards profile** (`relaxed` / `standard` / `strict`). The profile `validation_commands`
are the seed; the registry extends them (e.g. add `eslint`, `tsc`, `clippy`, `gofmt`,
`go vet`, `golangci-lint`, `ruff format --check`).

### Tests

Reuses the harness's existing TDD-first pre-gate and scoped test run, plus **test-gap
detection** from the graph: changed public symbols with no corresponding test file are
flagged (configurable: warn or block).

## Optional rules (opt-in hard standards)

**The default needs no rules file** — built-in regression detection (cycles, god-files,
coupling, health score) runs with zero config. This file is only for teams that want to go
beyond regression-catching: pin absolute thresholds, declare layers/boundaries, or set a
language to `strict`. A single declarative file, e.g. `.opencontext/quality.toml`:

```toml
enabled       = true        # master on/off switch for the architecture feature
max_fix_loops = 3           # self-correction budget: in-loop fix attempts before
                            # the regression is surfaced to the user (token guard)
mode          = "ratchet"   # off | warn | strict | ratchet
baseline      = ".opencontext/quality-baseline.json"

[architecture]
max_cycles    = 0
no_god_files  = true
max_cc        = 25
max_coupling  = "B"         # letter grade or numeric threshold

[[architecture.layers]]
name  = "core"
paths = ["packages/*/opencontext_core/**"]
order = 0

[[architecture.boundaries]]
from   = "core"
to     = "cli"
allow  = false
reason = "core must stay framework- and adapter-agnostic"

[languages.python]
profile = "strict"          # runs ruff check, ruff format --check, mypy, pytest
[languages.typescript]
profile = "standard"        # eslint, tsc --noEmit
[languages.go]
profile = "standard"        # gofmt -l, go vet, golangci-lint
```

Each rule carries a severity; `mode` sets the global posture and `ratchet` compares
against the baseline so only regressions block.

## Where it integrates

The **default and only required** integration is agent-time and automatic. Everything else
is an optional surface on the same engine, for teams that want it.

1. **Agent-time — the harness gate (default, automatic, zero-config).**
   - At run start (`explore`) capture the architecture-health snapshot automatically.
   - After **apply**, recompute on the changed scope and diff against the snapshot.
   - A regression is fed back to the agent, which self-corrects **in the same run** (like
     the existing test/verify feedback) — the user is not involved. Under `BudgetMode.STRICT`
     an unresolved regression fails the phase. This extends the existing gate-dispatch +
     `GGARulesPhase` machinery, not a parallel system.
   - Per-persona: the **Architect** sees health during *design*; the **Builder** gets the
     regression as actionable feedback during *apply*; the **Reviewer** confirms in
     *verify*/*review*.

2. **MCP — mid-edit self-check (optional, agent-driven).**
   - An `opencontext_quality` tool lets the agent check the changed scope while editing and
     self-correct before the gate even runs. Still no user action.

3. **CLI — optional, for humans who want a manual check.**
   - `opencontext quality check` / `gate --save` — evaluate / snapshot, exit `0`/`1`.
   - Shares the engine + (optional) rules with the in-loop gate — one source of truth.

4. **CI — optional merge-time gate.**
   - For teams that also want PRs blocked: add `opencontext quality check` to CI (surfaced
     via `ci-check`). Opt-in; the in-loop gate already protects the agent's own changes.

## Engine components

All four reuse existing subsystems; this is mostly wiring + a rules layer.

- **Architecture analyzer** — over `dependency_graph` / `call_graph` / `graph_analysis`:
  SCC for cycles, fan-in for god-files/coupling, path-matching for layers/boundaries,
  AST for complexity.
- **Language quality runner** — resolves the language → tool set (seeded by profile
  `validation_commands`), runs them via the existing `SafeCommand` execution over the
  changed scope, normalizes output.
- **Rules evaluator** — loads the config, evaluates analyzer + runner outputs, applies
  severities/thresholds, produces a verdict + per-finding detail.
- **Baseline / ratchet store** — saves a metrics+violations snapshot; diffs against it so
  only new violations block.
- **Reporter** — emits a normalized result into the harness gate, the CLI exit code, and
  the trace (so every decision is auditable).

## Adoption / ratchet strategy

1. Ship in `warn` — visible, non-blocking; teams see their findings.
2. `opencontext quality gate --save` captures the baseline.
3. Flip to `ratchet` — no **new** violations allowed; legacy untouched.
4. Tighten thresholds and burn down the baseline over time toward `strict`.

This makes the system adoptable on a real, imperfect codebase without halting work on day
one, while still **forcing** that things only get better.

## Phased plan

- **Phase 1 — MVP (architecture core + language quality via profiles).**
  - Architecture analyzer: `max_cycles`, `no_god_files`, `layers`/`boundaries`.
  - Language quality runner over profile `validation_commands` for the changed scope.
  - `quality.toml` schema + loader + baseline.
  - `opencontext quality gate --save|--check` (exit 0/1).
  - Harness gate in **warn** mode + trace output.

- **Phase 2 — enforcement.**
  - `strict`/`ratchet` enforcement in the harness (FAIL under `BudgetMode.STRICT`).
  - CI integration (`quality check` in the pipeline + `ci-check`).
  - `opencontext_quality` MCP tool.
  - Language → standards registry beyond profile defaults; `max_cc` from AST.

- **Phase 3 — depth.**
  - Duplication/redundancy and depth metrics; a single rolled-up quality score.
  - Per-persona wiring (Architect/Reviewer); evolution tracking across runs.

## Honest ceilings & risks

- **Measurable, not magic.** It enforces cycles, coupling, god-files, boundaries,
  complexity, lint/type/test standards — not subjective design quality.
- **Tool availability.** Per-language checks need the language's tools present. For a true
  forcing gate, required tools are declared and their absence is a configurable failure,
  not a silent pass.
- **Cost.** Running language tools over the changed scope adds time; keep it scoped to the
  diff, cache per file hash, and run architecture analysis incrementally off the graph.
- **Legacy false-positives.** Solved by the baseline/ratchet model.
- **Cross-language architecture** is limited to what the graph can parse; the language
  coverage tracks the indexer's language support.

### Token cost

Enforcement is **deterministic and native — there is no model in the check path** — so the
checks themselves cost **zero tokens** (graph analysis + subprocess linters/type-checkers).

- **Clean change → ~0 token overhead.** The gate passes without any model call.
- **Violation → bounded extra tokens.** Only when a rule fails does the agent run an extra
  fix iteration (model tokens), proportional to the fix. The violation report fed back is a
  compact `file:line:rule` structure, not raw tool output.
- **Net saver over time.** A degraded architecture costs more tokens on *every future
  task* (more files to read, larger context packs, tangled dependencies). Keeping the
  codebase clean keeps context packs small — fewer tokens per task — so enforcement
  *reduces* long-run consumption. It complements the adaptive retrieval budget and
  rehydration summarization.
- **Cost-control levers:** scope checks to the diff; feed compact reports (not raw linter
  dumps) into context; `ratchet` mode blocks only *new* violations so the agent never
  churns on legacy; run the gate once per phase (post-apply), not per edit. Note that
  subprocess linters add wall-clock latency, not tokens — a separate, smaller cost.

## What we reuse (already built)

This proposal is largely orchestration on top of existing capabilities:

- `dependency_graph`, `call_graph`, `graph_analysis` (centrality / fan-in) — architecture
  signals.
- tree-sitter AST parsing — complexity + structure.
- technology profiles + their `validation_commands` (`SafeCommand`) — per-language tools.
- harness gates, `BudgetMode.STRICT`, gate dispatch, `GGARulesPhase` — the enforcement
  mechanism and fail-closed posture.
- `quality` and `ci-check` commands — the CLI/CI surface to unify under one rules source.
- MCP server — to expose the check to the agent.
- trace + learning — auditability and (optionally) feeding the adaptive budget.

The net new work is: the **rules schema + evaluator**, the **architecture analyzer**
(cycles/god-files/boundaries/complexity), the **language standards registry**, the
**baseline/ratchet store**, and the **wiring** into harness/CLI/CI/MCP.

## Concrete design (implementation map)

Proposed home: a new `opencontext_core/quality/` package (one already exists for
`ci_checks.py` — extend it). Module layout:

```
opencontext_core/quality/
  rules.py        # config schema + loader (QualityRules, load_rules)
  architecture.py # ArchitectureAnalyzer over the knowledge graph
  languages.py    # LanguageStandards registry + LanguageQualityRunner
  evaluator.py    # QualityEvaluator: analyzer + runner -> verdict
  baseline.py     # BaselineStore (save/load/diff, ratchet)
  models.py       # Finding, RuleVerdict, QualityReport (reuse ci_checks enums)
  ci_checks.py    # (existing) — register architecture/quality as checks
```

Reuse, don't rebuild: `ci_checks.py` already defines `CheckSeverity`, `CheckStatus`,
`CheckResult`, `CheckDefinition`, `CheckRunner` — the new findings normalize into those,
so `opencontext ci-check run` and the new gate share one result type.

### Architecture analyzer (over the existing graph)

Inputs are already in the graph DB: `nodes(id, kind, file, line, …)` and
`edges(source_node_id, target_node_id, kind, call_site_file, call_site_line)`.

- **Cycles** (`max_cycles`): build a file-level (or module-level) directed graph from
  `edges` (kinds `from_import`/`import`/`calls`), run **Tarjan SCC**; any SCC with >1 node
  (or a self-loop) is a cycle. Report the participating files. `graph_analysis` has no
  `detect_cycles` yet — add Tarjan there (it already loads adjacency).
- **God-files / coupling** (`no_god_files`, `max_coupling`): use
  `graph_analysis.compute_centrality()` → `Centrality.in_degree`/`out_degree`. A god-file =
  in_degree above a threshold (derived from the distribution, e.g. > p95 or an absolute
  cap) and/or LOC over a cap. Coupling grade maps degree bands to A–F.
- **Layers / boundaries**: glob-match each node's `file` to a layer; for every edge, if the
  (source layer → target layer) pair is disallowed by a `[[boundaries]]` rule, it's a
  violation. Pure path + edge lookup, no new parsing.
- **Complexity** (`max_cc`): per-symbol cyclomatic complexity from the tree-sitter AST we
  already parse (count branch/loop/boolean-op nodes per function via a small per-language
  query). Start with Python; extend per language.

All of this is deterministic and reads the graph that `index` already builds — **zero
model calls, no re-parse beyond complexity**.

### Language standards runner

`LanguageStandards` registry maps `language -> [tool specs]`, seeded by the profiles'
existing `validation_commands` (`SafeCommand`) and extended (ruff/mypy/ruff-format,
eslint/tsc, gofmt/go vet/golangci-lint, clippy/rustfmt, phpstan/phpcs/pint, …). Each tool
spec declares: command, how to scope to files, parser (exit-code or regex/JSON → findings),
and whether it is `required` for the project's `mode`.

`LanguageQualityRunner`:
1. Resolve languages of the changed files (technology profiles + extension map).
2. Run each language's tools over the **diff scope** via the existing `SafeCommand`
   execution (already sandbysed/allowlisted).
3. Normalize stdout/exit → `Finding(file, line, rule, severity, message)`.
4. Missing required tool → a `tool_missing` finding (configurable: block or skip).

### Evaluator + finding model

`QualityEvaluator.evaluate(changed_files, rules, baseline) -> QualityReport`:
- runs ArchitectureAnalyzer + LanguageQualityRunner,
- applies per-rule severity + thresholds,
- in `ratchet`, filters out findings present in the baseline (only **new** ones count),
- returns a `QualityReport(findings, score, status)` where `status` maps to the harness
  `GateStatus` (FAILED/WARNING/PASSED) and to a CLI exit code.

### Baseline / ratchet store

`.opencontext/quality-baseline.json`: `{ "findings": [ {key, file, rule, severity} ],
"metrics": {cycles, god_files, max_cc, …}, "generated_at" }`. Finding **key** =
`sha1(rule + normalized_file + symbol_or_line_bucket)` so cosmetic line shifts don't churn.
Diff: `new = current_keys − baseline_keys`. `gate --save` writes it; `ratchet` mode blocks
only on `new`.

### Harness integration

- Declare an `architecture_clean` (and `quality_standards`) gate in the verify (and/or
  apply) phase config. The runner's `_dispatch_declared_gates(...)` already routes by
  `gate_id` — add a branch that calls `QualityEvaluator` and returns a `PhaseGate`.
- Capture the baseline at **explore** (run start) into run state; evaluate after **apply**.
- Under `BudgetMode.STRICT` a FAILED quality gate fails the phase (the fix loop kicks in);
  otherwise it's a WARNING. Findings go into the trace + are surfaced to the Builder for the
  fix iteration.

### CLI / CI

- `opencontext quality gate --save` → write baseline.
- `opencontext quality check [--json] [--diff]` → evaluate; exit `0` (clean) / `1`
  (violation). Human table + `--json` for CI.
- Register the architecture/quality evaluation as discoverable `ci-check` definitions so
  `opencontext ci-check run` covers it too — one rules source, two entry points.
- Add `opencontext quality check` to the project's CI workflow (and OpenContext's own
  `test.yml`, dogfood).

### MCP tool

`opencontext_quality` (args: `scope` = `diff|all`, optional `rules`): returns the
`QualityReport` (findings + score). Lets the agent self-check mid-apply before the gate.
Registered like the other 14 tools in `mcp_stdio`.

## Open decisions (need a call before building)

Settled by the zero-config / in-loop direction:

- **Default behavior**: in-loop, automatic, **regression-based (ratchet)** with built-in
  signals — no rules file, the agent self-corrects. `strict` (hard block) and absolute
  thresholds are opt-in. CLI/CI are optional surfaces.
- **Built-in signal set** (no config): new cycles, new god-file, worsened coupling, health
  score drop. These need no user input.
- **User controls** = two config keys: `enabled` (on/off) and `max_fix_loops` (token guard
  on self-correction). Both default sensibly; nothing else is required.

Still genuinely open:

1. **Health score formula** — how the built-in signals roll into one number + what counts
   as a "drop". Needs to be stable, explainable, and cheap. (The headline UX is this score.)
2. **`max_fix_loops` default** — the out-of-the-box value (e.g. 2–3) before surfacing the
   regression to the user.
3. **Optional rules location** — standalone `.opencontext/quality.toml` vs a `quality:` block
   in `opencontext.yaml`. (Lean: standalone toml.)
4. **Optional language tool depth** — when a project opts into `strict`, which extra tools
   per language beyond the profile defaults, and missing-tool policy (block vs notice).
5. **Architecture granularity** — file-level vs module/package-level cycles & layers.
   (Lean: file-level first.)
6. **Monorepo / multi-language** per-subtree rules. (Defer; single root first.)

## Acceptance criteria

- A change that introduces an import cycle **fails** `opencontext quality check` (exit 1)
  and, in `strict`, fails the harness verify gate.
- `gate --save` then a clean change → exit 0; a new god-file/boundary violation → exit 1;
  a *pre-existing* violation under `ratchet` → exit 0 (not blocked).
- Per-language lint/type findings on changed files are reported and gate-enforced where the
  tool is present; a missing required tool is reported, never a silent pass.
- Deterministic: same inputs → same report. Zero model calls in the check path.
- Perf: architecture analysis is incremental off the graph; language tools run on the diff;
  a typical change evaluates in seconds, not minutes.
- Dogfood: OpenContext's own repo passes its own `quality check` in CI.

## Sequencing & rough effort

- **Phase 1 (MVP, ~medium):** `rules.py` + `architecture.py` (cycles/god-files/boundaries) +
  `languages.py` seeded from profiles + `baseline.py` + `opencontext quality gate/check`
  CLI + harness gate in **warn**. Ship behind `mode=off` default until validated.
- **Phase 2 (~medium):** STRICT/ratchet enforcement in harness + CI wiring + MCP tool +
  complexity (`max_cc`) + richer language registry.
- **Phase 3 (~larger):** duplication/depth metrics + rolled-up score + per-persona wiring +
  evolution tracking.

Each phase is a self-contained SDD change with its own tests; Phase 1 delivers a usable,
honest `quality check` even before enforcement is turned on.
