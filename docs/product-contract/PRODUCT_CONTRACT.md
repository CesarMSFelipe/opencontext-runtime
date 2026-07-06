# PRODUCT_CONTRACT

OpenContext is a local-first agentic runtime that operates over repositories: it indexes code
into a knowledge graph, builds token-budgeted context packs, persists agentic memory, and runs
verifiable engineering workflows (OC Flow, SDD, TDD strict) through a gated harness. It runs on
the user's machine, uses the agent client's provider, and produces evidence for every run.

Verified by: AC-001..AC-030, SMOKE-001..SMOKE-010.

## Command maturity tiers

| Tier | Meaning | Guarantees |
|---|---|---|
| `stable` | Public product API for humans and agents | JSON contract, exit-code contract, semver compatibility, acceptance coverage |
| `preview` | Usable but contract may change | Documented, may change between minor versions, excluded from acceptance gate |
| `internal` | Implementation/diagnostic surface | No contract; hidden from primary `--help`; may change or disappear anytime |

Rules: no `stable` command without a JSON contract; no `stable` command that prints placeholders;
`preview`/`internal` commands must not be presented as stable in the main help.

## Stable command list

`version`, `doctor`, `status`, `init`, `install`, `uninstall`, `clean`, `config`, `index`,
`pack`, `run`, `runs`, `sdd`, `harness`, `memory`, `knowledge-graph`, `tui`.

All other top-level commands (e.g. `loop`, `studio`, `simulate`, `benchmark`, `evolve`,
`mutation`, `persona`, ...) are `preview` or `internal` until explicitly promoted.

> `tui` ships as a top-level command: `opencontext tui [root] [--smoke]` opens the home
> dashboard (runs, SDD workspace, doctor, config inspector, uninstall preview); `--smoke`
> is the headless CI boot check. The release gate must verify each entry in the list exists.

## Mandatory flows

| Flow | Commands | Expected end state |
|---|---|---|
| First use | `pipx install …` → `init` → `doctor` → `status` | workspace valid, doctor clean, actionable next step |
| OC Flow bugfix, no executor | `run "<task>" --json` without productive executor | `needs_executor` (never `passed`) |
| OC Flow bugfix, with executor | `run "<task>" --json` with executor | `passed` with diff + verification evidence, or `failed` |
| SDD full cycle | `sdd new → explore → propose → spec → design → tasks → apply → verify → archive` | `archived`, artifacts connected, no artifact lost |
| Memory reuse | run 1 saves memory → run 2 reports it as a hit | `memory.hits[]` present in run 2 `run.json` |
| Uninstall purge | `uninstall --scope workspace --purge --verify` | no managed residue; unmanaged paths reported, not deleted |

## Canonical final states

`passed`, `failed`, `blocked`, `needs_executor`, `needs_approval`, `needs_context`,
`needs_configuration`, `not_applicable`, `cancelled`. No stable command may emit any other
final state. Full semantics: see `RUN_STATE_CONTRACT.md`.

## Evidence requirements

- Every run persists artifacts under `.opencontext/runs/<run_id>/` (see `SDD_CONTRACT.md` §Runs
  and the harness artifact list): `run.json`, `gates.json`, `context-pack.json`,
  `memory_delta.json`, `graph_delta.json`, `events.json`, `receipts/`.
- `passed` requires evidence: executed verification commands, gate results, and (when mutation
  was required) the applied diff. No evidence → the state is not `passed`.
- `report` artifacts and `run.json` must tell the same story (same status, same changed files).
- TDD strict runs additionally require RED and GREEN evidence (`TDD_STRICT_CONTRACT.md`).

## Definition of Done

The product is done when all of the following hold, each proven by the listed test IDs:

| # | Criterion | Verified by |
|---|---|---|
| 1 | Published package installs in a clean environment | AC-030, SMOKE-001 |
| 2 | `version` / `status` / `doctor` / `config` are consistent and JSON-clean | AC-001, AC-002, AC-004 |
| 3 | `init` / `install` prepare a workspace with expected state | AC-003, SMOKE-003 |
| 4 | `index` builds a minimal knowledge graph | AC-005, SMOKE-004 |
| 5 | `pack` uses KG, memory, and compression with metrics | AC-007, AC-008, SMOKE-005 |
| 6 | OC Flow works with and without an executor | AC-009, AC-010, AC-011 |
| 7 | SDD works end to end, `new` through `archive`, without losing artifacts | AC-014, AC-015, AC-016 |
| 8 | TDD strict proves RED → GREEN | AC-012, AC-013, SMOKE-009 |
| 9 | Memory is saved, approved, reused, compacted, purged | AC-017, AC-018, AC-019 |
| 10 | TUI shows and operates runs, SDD, config, memory, KG, uninstall | TUI-AC-001..008 |
| 11 | `config explain` shows exact precedence per key | CFG-007 |
| 12 | Uninstall purges managed residue in all scopes | AC-022, AC-023, SMOKE-010 |
| 13 | External acceptance harness passes against the installed package | AC-030 |
| 14 | Exit codes are reliable and match states | AC-011, AC-024 |
| 15 | No mixed human text in `--json` stdout | AC-001, AC-002, AC-024 |
| 16 | No placeholder stable commands | AC-024, release gate |
| 17 | Release produces an evidence report (version, checksum, acceptance summary) | AC-029, RELEASE_CONTRACT |

## Freeze rule

No new subsystem may be added until the acceptance suite (`ACCEPTANCE_CONTRACT.md`) passes
against the installed package. Progress is measured by acceptance tests, not by implementation.
