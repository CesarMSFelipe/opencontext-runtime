# 60 — Convergence-2 Transversal Addenda

Authority: architecture review (2nd pass). The review named **3 imprescindible** gaps — handled
elsewhere: Compatibility Layer (`.sdd/changes/pr-000-0-compatibility-layer/`), Dependency Map
(doc 58), Internal Contracts (doc 59). The remaining review items are **non-blocking reinforcements**.
Per the review's own guidance ("no añadiría más PR funcionales"), they are **NOT new PRs** — each
folds into an existing PR's spec as an addendum requirement. This doc is the assignment ledger so
nothing is lost and planning does not loop.

| # | Reinforcement | Owning PR | Requirement to fold (status: PROPOSED unless noted) |
|---|---------------|-----------|------------------------------------------------------|
| 5 | Diagnostics as a reusable subsystem | PR-007 (extract) + reused by PR-011 | Extract diagnosis (reproduce→hypothesis→instrument→verify→root-cause→decision) out of the OC Flow node into a standalone `diagnostics/` subsystem so SDD, OC Flow and Runtime Intelligence can reuse it. |
| 6 | Runtime Brain restrictions | PR-000.1 | Codified in doc 59 (Decision API invariant); add the no-write-port construction + guard test to PR-000.1 spec. |
| 7 | Event hierarchy (11 families) | PR-001/PR-002 | `RuntimeEvent.family` required enum; Studio renders per-family lanes. (doc 59) |
| 8 | Global IDs | PR-001 | Single `runtime/ids.py` factory; prefixed ULID/hash scheme. (doc 59) |
| 9 | Context Ranking (4th layer) | PR-010 | Add a Ranking stage after retrieval (KG/Memory/Cache/Compression → **Rank** → assemble). Retrieval is not enough; prioritize before budgeting. |
| 10 | Scheduler can simulate | PR-000.1 + PR-011 | `Scheduler.simulate(plan) -> {estimated_cost, estimated_confidence, estimated_time}` before execution; reuses Runtime Simulator. |
| 11 | Unified Resource Budget | PR-010 (model) + PR-001 (enforce) | One `ResourceBudget{token, tool, context, time, retry, mutation}` replacing the lone token budget; enforced per node. |
| 12 | Observability timelines | PR-014 (view) over PR-002 (data) | Execution / decision / context / memory / KG timelines derived from the event families (#7); Studio renders them. |
| 13 | Plugin lifecycle (full) | PR-015 | `install → validate → enable → upgrade → disable → remove → migrate` state machine (extends current install/registry). |
| 14 | SDK conformance tests | PR-015 | A conformance suite a plugin runs to prove it honors the public contracts before activation. |
| 15 | 100-consecutive-runs benchmark | PR-017 | Degradation/stability benchmark (cache, memory growth, index growth, latency drift) beyond single first-run. |

## Application rule

These addenda are folded into the named PR's `spec.md` (a `## SPEC <PRID>-CONV2` section) when
that PR reaches implementation in its wave — NOT pre-emptively re-edited across all specs now
(avoids the endless-planning trap the review warns against). The owning PR's builder reads this
ledger as part of its scope.

## Not adopted as separate work

Internal versioning (#4) → doc 59. Items 1–3 → their dedicated artifacts. No item becomes a new
functional PR. Total scope delta: 0 new PRs, 11 folded requirements.
