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
