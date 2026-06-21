# Architecture & Code-Quality Enforcement — Planning Document

Status: **proposal** (not implemented). Owner: TBD. Target: a new minor release.

## 1. Goal

Give OpenContext a **native, forcing** quality layer: a system that makes every change
the agent produces meet **architecture standards** (cross-language) and **per-language
code-quality standards**, fail-closed, at the moment of change and again at merge — so the
codebase cannot silently degrade as the agent works at machine speed.

"Forcing" means: when a rule is violated in strict mode, the work is **blocked**, not
warned. The agent must fix it before the change is accepted.

### Non-goals

- Not aesthetic or subjective "perfect design" — we enforce the **measurable**.
- Not a replacement for each language's own linters/type-checkers — we **orchestrate and
  enforce** them, we do not reimplement them.
- Not runtime/performance profiling.
- Not an external service or binary dependency — it is native and client-side.

## 2. Principles

- **Native + client-side.** Runs on the data and tools we already have; no new runtime
  dependency, no model in the enforcement path (deterministic).
- **Language-agnostic core + per-language adapters.** Architecture rules work off the
  knowledge graph (any indexed language); code-quality rules delegate to each language's
  canonical tools.
- **Fail-closed in strict mode**, advisory otherwise. Severity is per-rule.
- **Baseline / ratchet adoption.** Capture a baseline; block *new* violations even when
  legacy ones exist. Teams adopt without a big-bang cleanup, then tighten over time.
- **Degrade honestly.** If a required language tool is absent, say so explicitly — never
  report "pass" for a check that did not run. (For a true forcing gate, missing required
  tools is a configurable failure, not a silent skip.)
- **One contract, many enforcement points.** The same rules drive the agent loop, the CLI,
  and CI — no drift between "what the agent checks" and "what the PR checks".

## 3. What it enforces

### 3.1 Architecture (cross-language, from the knowledge graph)

Computed from the existing `dependency_graph` + `call_graph` + `graph_analysis`:

| Rule | Meaning | Source signal |
|------|---------|---------------|
| `max_cycles` | No new import/call cycles | strongly-connected components (Tarjan) over the dependency graph |
| `no_god_files` | No file/symbol with excessive fan-in or size | `graph_analysis` centrality (in-degree / fan-in) + LOC |
| `layers` / `boundaries` | Declared layers may only depend in the allowed direction | path-matched edges in the dependency graph |
| `max_coupling` | Cap on fan-in/fan-out per module | `graph_analysis` degrees |
| `max_complexity` (`max_cc`) | Cyclomatic complexity per symbol | tree-sitter AST (branch/loop counting) |
| `max_depth` | Directory / nesting depth ceiling | path analysis |

### 3.2 Per-language code quality (delegated to each language's tools)

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

### 3.3 Tests

Reuses the harness's existing TDD-first pre-gate and scoped test run, plus **test-gap
detection** from the graph: changed public symbols with no corresponding test file are
flagged (configurable: warn or block).

## 4. Rules configuration

A single declarative file, e.g. `.opencontext/quality.toml` (or a `quality:` block in
`opencontext.yaml`), version-controlled with the project:

```toml
mode = "ratchet"            # off | warn | strict | ratchet
baseline = ".opencontext/quality-baseline.json"

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

## 5. Where it integrates (the forcing points)

The same engine runs at three points, driven by the same config:

1. **Agent-time — the harness gate (primary forcing function).**
   - At run start (explore) capture the quality baseline.
   - After **apply**, before **verify** completes, run the engine over the changed scope.
   - In `strict`/`ratchet` mode under `BudgetMode.STRICT`, a violation makes the phase
     **FAIL** → the agent cannot close the change until it is fixed. This extends the
     existing gate-dispatch + `GGARulesPhase` machinery rather than adding a parallel one.
   - Per-persona: the **Architect** consults the rules during *design*; the **Builder**
     gets violations as actionable feedback during *apply*; the **Reviewer** enforces in
     *verify*/*review*.

2. **CLI — standalone + scriptable.**
   - `opencontext quality gate --save` — snapshot the baseline.
   - `opencontext quality gate` / `opencontext quality check` — evaluate, exit `0`/`1`.
   - Unifies with the existing `quality` and `ci-check` commands (one rules source).

3. **Merge-time — CI.**
   - Add `opencontext quality check` to the project's CI (and surface it via `ci-check`),
     so a PR that degrades architecture or violates language standards **cannot merge**.
   - Dogfood: wire it into OpenContext's own `test.yml`.

4. **MCP — mid-edit self-correction.**
   - Expose an `opencontext_quality` tool so the agent (inside its editor) can check the
     changed scope while editing and self-correct before the gate runs.

## 6. Engine components

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

## 7. Adoption / ratchet strategy

1. Ship in `warn` — visible, non-blocking; teams see their findings.
2. `opencontext quality gate --save` captures the baseline.
3. Flip to `ratchet` — no **new** violations allowed; legacy untouched.
4. Tighten thresholds and burn down the baseline over time toward `strict`.

This makes the system adoptable on a real, imperfect codebase without halting work on day
one, while still **forcing** that things only get better.

## 8. Phased plan

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

## 9. Honest ceilings & risks

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

## 10. What we reuse (already built)

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

## 11. Concrete design (implementation map)

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

### 11.1 Architecture analyzer (over the existing graph)

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

### 11.2 Language standards runner

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

### 11.3 Evaluator + finding model

`QualityEvaluator.evaluate(changed_files, rules, baseline) -> QualityReport`:
- runs ArchitectureAnalyzer + LanguageQualityRunner,
- applies per-rule severity + thresholds,
- in `ratchet`, filters out findings present in the baseline (only **new** ones count),
- returns a `QualityReport(findings, score, status)` where `status` maps to the harness
  `GateStatus` (FAILED/WARNING/PASSED) and to a CLI exit code.

### 11.4 Baseline / ratchet store

`.opencontext/quality-baseline.json`: `{ "findings": [ {key, file, rule, severity} ],
"metrics": {cycles, god_files, max_cc, …}, "generated_at" }`. Finding **key** =
`sha1(rule + normalized_file + symbol_or_line_bucket)` so cosmetic line shifts don't churn.
Diff: `new = current_keys − baseline_keys`. `gate --save` writes it; `ratchet` mode blocks
only on `new`.

### 11.5 Harness integration

- Declare an `architecture_clean` (and `quality_standards`) gate in the verify (and/or
  apply) phase config. The runner's `_dispatch_declared_gates(...)` already routes by
  `gate_id` — add a branch that calls `QualityEvaluator` and returns a `PhaseGate`.
- Capture the baseline at **explore** (run start) into run state; evaluate after **apply**.
- Under `BudgetMode.STRICT` a FAILED quality gate fails the phase (the fix loop kicks in);
  otherwise it's a WARNING. Findings go into the trace + are surfaced to the Builder for the
  fix iteration.

### 11.6 CLI / CI

- `opencontext quality gate --save` → write baseline.
- `opencontext quality check [--json] [--diff]` → evaluate; exit `0` (clean) / `1`
  (violation). Human table + `--json` for CI.
- Register the architecture/quality evaluation as discoverable `ci-check` definitions so
  `opencontext ci-check run` covers it too — one rules source, two entry points.
- Add `opencontext quality check` to the project's CI workflow (and OpenContext's own
  `test.yml`, dogfood).

### 11.7 MCP tool

`opencontext_quality` (args: `scope` = `diff|all`, optional `rules`): returns the
`QualityReport` (findings + score). Lets the agent self-check mid-apply before the gate.
Registered like the other 14 tools in `mcp_stdio`.

## 12. Open decisions (need a call before building)

1. **Rules location**: standalone `.opencontext/quality.toml` vs a `quality:` block in
   `opencontext.yaml`. (Lean: standalone toml — co-located, diffable, matches the
   per-project convention.)
2. **MVP rule set**: which rules ship enforcing first. (Lean: `max_cycles=0` +
   `no_god_files` + `boundaries` + per-language lint/type via profile commands.)
3. **Default mode** out of the box: `off` / `warn` / `ratchet`. (Lean: `warn`, so adoption
   never blocks day one; teams opt into `ratchet`/`strict`.)
4. **Missing-tool policy** for a required language tool: block vs skip-with-notice. (Lean:
   skip-with-notice by default; `strict` makes it a block.)
5. **Granularity of architecture** (file-level vs module/package-level cycles & layers).
   (Lean: file-level MVP, module-level as a follow-up.)
6. **Monorepo / multi-language**: per-subtree rules? (Defer; single root rules first.)
7. **Layer seeding**: hand-authored `[[layers]]` vs inferred from the dependency graph.
   (Lean: hand-authored MVP; offer an `infer` helper later.)

## 13. Acceptance criteria

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

## 14. Sequencing & rough effort

- **Phase 1 (MVP, ~medium):** `rules.py` + `architecture.py` (cycles/god-files/boundaries) +
  `languages.py` seeded from profiles + `baseline.py` + `opencontext quality gate/check`
  CLI + harness gate in **warn**. Ship behind `mode=off` default until validated.
- **Phase 2 (~medium):** STRICT/ratchet enforcement in harness + CI wiring + MCP tool +
  complexity (`max_cc`) + richer language registry.
- **Phase 3 (~larger):** duplication/depth metrics + rolled-up score + per-persona wiring +
  evolution tracking.

Each phase is a self-contained SDD change with its own tests; Phase 1 delivers a usable,
honest `quality check` even before enforcement is turned on.
