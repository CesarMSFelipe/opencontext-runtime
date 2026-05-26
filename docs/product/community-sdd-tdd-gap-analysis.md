# Community SDD/TDD + Multi-Agent Gap Analysis

OpenContext Runtime is the project-local context runtime, knowledge graph, safety layer, and measurable harness for coding agents. The product goal is compact context, reliable SDD/TDD loops, safe delegation, and verifiable token savings.

## Capability matrix

| Area | OpenContext status | Product direction |
|---|---|---|
| Code graph | Implemented: SQLite/FTS5 knowledge graph, MCP tools, callers/callees/impact, route detection | Keep as primary differentiator; every SDD/TDD phase should request graph-grounded context first |
| Agent support | Global installer supports 13+ agents; project-local `agent init` now covers the same community target set | Continue adding agent-native paths without moving SDK/provider code into core |
| SDD lifecycle | Core DAG supports explore → propose → spec → design → tasks → apply → verify → archive | Add SDD init/onboard commands as first-class runtime workflows if they are not only installer artifacts |
| TDD discipline | Tests and validation docs exist; agent instructions now explicitly require closest failing test before implementation when harness exists | Add automatic testing-capability detection to SDD init artifacts and phase prompts |
| Multi-agent orchestration | Core has delegation primitives, DAG state, token manager, and artifact stores; some execution paths remain scaffolded | Convert scaffolded execution into honest planner + adapters with traceable receipts before enabling real tool calls |
| Harness | Preflight, permissions, backups, rollback, golden tests | Controlled harness, quality gates, action policy, traces, ContextBench, backups/update/plugin systems exist |
| Token efficiency | Repo-map-first packing, context budgets, omission reasons, cache-aware prompt docs, ContextBench token-reduction gates | Make token ledger visible per SDD phase and fail when a phase exceeds configured budgets |
| Community usability | Installers, docs, quickstart, presets | README/docs are broad; project-local agent files concise |

## Minimum community-ready loop

1. `opencontext onboard .` creates config, index, hints, CI checks, and project-local agent guidance.
2. `opencontext sdd init --max-tokens 3000` detects local test/validation capabilities and writes `.opencontext/sdd/context.json` plus `.opencontext/sdd/testing.md`.
   Note: `sdd init` is not deprecated — use it to bootstrap SDD context before running `harness run`.
3. `opencontext index .` builds the knowledge graph.
4. `opencontext pack . --query "<change>" --mode plan --max-tokens 3000` creates phase context.
5. SDD runs through explore/propose/spec/design/tasks/apply/verify/archive.
6. Apply phase writes or updates focused tests first when a test runner is detected.
7. Verify phase runs focused tests, then broader configured checks.
8. `opencontext harness run --workflow sdd --task "<change>" --budget-mode warn` reports strict-TDD status, test capabilities, per-phase token ledger, and phase gates.
9. ContextBench records expected source coverage and token reduction.

## Non-negotiable quality gates

- No real external provider calls in tests.
- Core remains provider-neutral and free of CLI/FastAPI imports.
- Every edit path should preserve trace ids, selected/omitted context, token estimates, and approval decisions.
- Multi-agent delegation must use bounded tasks, disjoint file ownership, and independent verification.

## First implemented product increment

- `opencontext_core.sdd_runtime` detects Python, Node, Go, and Rust test capabilities without executing them.
- `opencontext sdd init` writes compact SDD/TDD artifacts for agents and users.
- `opencontext harness run --workflow sdd` now reports strict-TDD status, verification capabilities, per-phase token ledgers, and phase gates so token budget drift is visible.

## Related product UX

See [Installation Experience](installation-experience.md) for the setup target: select agents, choose TDD mode, create SDD artifacts, configure clients, and index the graph in one wizard run.
