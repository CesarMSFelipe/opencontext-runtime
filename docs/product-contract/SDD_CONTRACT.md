# SDD_CONTRACT

SDD (Spec-Driven Development) is a connected cycle with persistent artifacts — each phase
consumes the previous phase's output. No phase may print placeholders or lose artifacts.

Verified by: AC-014, AC-015, AC-016, SDD-001..SDD-012, TDD-007.

## Command surface (real)

```
opencontext sdd init | new | explore | propose | spec | design | tasks
                | apply | verify | archive | status | continue | ff | onboard | list
```

- `init` bootstraps SDD context for the project; `new <change>` scaffolds a change.
- `ff` fast-forwards planning (proposal → spec → design → tasks).
- `continue` runs the next dependency-ready phase; `status` reports structured state.
- `list` enumerates active changes; `onboard` is a guided walkthrough.

## Artifact structure (real layout)

Project-level SDD context:

```
.opencontext/sdd/
├── context.json      # stack, artifact store mode, testing capabilities
└── testing.md
```

Per-change artifacts (artifact store `openspec`/`hybrid`):

```
openspec/changes/<change>/
├── proposal.md
├── specs/<capability>/spec.md
├── design.md
├── tasks.md            # checklist; unchecked items => state "partial"
└── verify-report.md    # verdict + failure reasons
```

Apply/verify execution runs persist under `.opencontext/runs/<run_id>/` via the shared harness:
`run.json`, `gates.json`, `context-pack.json`, `events.json`, `memory_delta.json`,
`graph_delta.json`, `decisions.json`, `ledger.json`, `receipts/`, `archive-report.json`;
phase handoffs as `handoff.<phase>.json` + `state.json`; run index at
`.opencontext/runs/index.json`.

> Current → Target additions: per-change `manifest.json` (cycle metadata + state-machine
> position), `exploration.md` persisted by `explore`, an `apply_runs/` link list connecting the
> change to its harness run IDs, and `verification.json` (machine-readable twin of
> `verify-report.md`). Artifact stores `engram` and `none` exist; `status` must resolve from
> the active store instead of assuming files.

## State machine

```
draft → explored → proposed → specified → designed → tasked → applying → verified → archived
```

Plus terminal/exception states: `blocked`, `failed`. Rules:

- Transitions are forward-only along the chain; re-running a phase revises its artifact but
  cannot skip a missing predecessor.
- `blocked` is entered when a required artifact is missing/inconsistent (exit code 7, error
  envelope names the missing file and the corrective command).
- `failed` is entered when apply/verify gates fail (exit code 8).

## Rules

| Rule | Enforcement |
|---|---|
| Each phase consumes the previous phase's artifact | phase refuses to run with `missing:<artifact>` (exit 7) |
| `design` requires a valid spec; `apply` requires tasks | status resolver blocks (`blockedReasons`) |
| `apply` uses the same harness as OC Flow | apply produces a normal run under `.opencontext/runs/` |
| `verify` uses the same verification engine | verify executes real commands, records evidence |
| TDD strict honored during `apply` | RED → GREEN per `TDD_STRICT_CONTRACT.md` |
| No phase may lose artifacts | AC-016 regression |
| `continue` resumes from the last incomplete phase | dependency-ready resolution, no duplicates |
| `status --json` is machine-readable | reports change, artifact states, `nextRecommended`, `blockedReasons` |

## Status JSON (contract fields)

`sdd status --json` returns at minimum: `artifactStore` (`openspec|engram|hybrid|none`),
`artifactPaths`, `artifacts` (per-artifact `done|partial|missing`), `applyState`,
`nextRecommended`, `blockedReasons`. Routing consumers must use `nextRecommended` and
`blockedReasons`, never free text.

> Current → Target: the plan's `.opencontext/sdd/<cycle_id>/` layout is superseded by the real
> `openspec/changes/<change>/` store documented above; contracts and acceptance tests must
> target the real layout. A `review` phase verb (plan doc) does not exist and is not promised.
