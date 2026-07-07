# SDD_CONTRACT

SDD (Spec-Driven Development) is a connected cycle with persistent artifacts — each phase
consumes the previous phase's output. No phase may print placeholders or lose artifacts.

Verified by: AC-014, AC-015, AC-016, SDD-001..SDD-012, TDD-007.

## Command surface (real)

```
opencontext sdd init | new | explore | propose | spec | design | tasks
                | apply | verify | archive | status | continue | ff | onboard | list
```

- `init` bootstraps the SDD structure: the openspec scaffold AND the project SDD
  context (`.opencontext/sdd/context.json` + `testing.md`, created only when missing —
  install/wizard settings are never overwritten) plus the change registry.
- `new <change>` scaffolds a change, registers it in the registry, and writes its
  per-change `manifest.json` (state-machine position).
- `ff` fast-forwards planning (proposal → spec → design → tasks).
- `continue` resolves the disk status and dispatches the next dependency-ready phase
  (dispatcher markdown + the phase prompt — never a static, phase-less prompt).
- `status` reports structured state; `list` enumerates active changes (the closed
  `archive/` folder is excluded); `onboard` is a guided walkthrough.
- `apply --execute` runs the shared OC Flow harness (same entry as
  `opencontext run --workflow sdd`); blocked (exit 7) when the change is not apply-ready.
- `archive` closes a verified change: moves it under `openspec/changes/archive/<date>-<change>/`
  preserving every evidence artifact plus an `archive-report.json` inventory; without a
  passing verify-report it blocks with exit 7 and moves nothing.

## Artifact structure (real layout)

Project-level SDD context:

```
.opencontext/sdd/
├── context.json      # stack, artifact store mode, testing capabilities
├── testing.md
└── registry.json     # known changes → state-machine position + path
```

Per-change artifacts (artifact store `openspec`/`hybrid`):

```
openspec/changes/<change>/
├── proposal.md
├── manifest.json       # cycle metadata + state-machine position
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

The harness run bundle additionally persists `exploration.md` (explore findings, consumed
by propose and carried into `proposal.json`) and `acceptance.md` (the spec's GIVEN/WHEN/THEN
scenarios) alongside `spec.md`/`design.md`/`tasks.json`.

> Current → Target additions (remaining): an `apply_runs/` link list connecting the change to
> its harness run IDs, and `verification.json` (machine-readable twin of `verify-report.md`).
> The plan's per-change `problem.md`/`specification.md` names are superseded by the real
> `proposal.md`/`specs/<cap>/spec.md` artifacts. Artifact stores `engram` and `none` exist;
> `status` must resolve from the active store instead of assuming files.

## State machine

```
draft → explored → proposed → specified → designed → tasked/applying → verified → reviewed → archived
```

Plus terminal/exception states: `blocked`, `failed`. The resolver derives the position
from disk artifacts (`Status.cycleState`): unchecked tasks are `applying`, a fully
checked list is `tasked`, a passing verify-report is `verified` (`reviewed` once a
review-report exists), a FAIL verdict is `failed`. Rules:

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
| `apply` uses the same harness as OC Flow | `sdd apply --execute` / `run --workflow sdd` produce a normal run under `.opencontext/runs/` |
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

Additive operational fields (additive JSON only — never renamed/removed): `cycleState`
(state-machine position above), `currentPhase` (the phase the cycle is in), `gates`
(gate summaries from the newest `.opencontext/runs/<id>/gates.json`; empty when no run
evidence exists — never fabricated) and `gatesRun` (the run id those gates came from).

> Current → Target: the plan's `.opencontext/sdd/<cycle_id>/` layout is superseded by the real
> `openspec/changes/<change>/` store documented above; contracts and acceptance tests must
> target the real layout. The `review` verb performs the honest structural review
> (`review-report.json` + `review.md`); a missing change exits 7.
