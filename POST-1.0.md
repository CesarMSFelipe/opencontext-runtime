# POST-1.0 Backlog

Items deliberately deferred past the OpenContext 1.0 release. Each was triaged during the
SDD change `1.0-productization-correctness` (PROD-005 / PROD-006, B5 / B6) and is honestly
**not built for 1.0** — it is recorded here with a rationale rather than faked as complete on
its archived task board.

Authority: spec `1.0-productization-correctness` PROD-005 Deferral Ledger + PROD-006 task
reconciliation. Source boards:
`.sdd/archive/2026-06-29-architecture-verification-hardening/tasks.md` and
`.sdd/archive/2026-06-29-vnext-default-migration/tasks.md`.

> Distinction: the B5 **build-core** artifacts (externalized `architecture-baseline.json`,
> `compat/architecture_diff.py`, the `opencontext architecture diff` command, and the ADR
> *section-presence* guard `test_adr_doc_sections.py`) are **NOT** deferred — they are built by
> `1.0-productization-correctness` itself and remain tracked as OPEN on the arch-verification board.
> Only the items below are genuinely deferred.

## Deferred items

| # | Item | Source task | Rationale |
|---|------|-------------|-----------|
| 1 | **`audit-verdicts.md`** — Built==Functional audit artifact (WIRED / INERT / SKELETON verdicts with file:line evidence, one requirement per major subsystem) | arch-verification 7.17 | Lowest-value remaining B5 artifact; explicitly listed in the spec PROD-005 Deferral Ledger. The live fitness guards (`test_no_contract_drift.py`, `test_no_direct_memory_writes.py`, `test_no_direct_provider_calls.py`) already enforce the load-bearing Built==Functional invariants mechanically, so the narrative audit doc is documentation, not a release gate. File absent today. |
| 2 | **ADR prose entries** — ADR-A1 (OC Flow completion-status state machine) + ADR-A2 (canonical config location) + entries for the 4 new fitness guards in `docs/.../18-architecture-decision-records.md` | arch-verification 7.16 | The ADR *section-presence guard* (7.6) ships in 1.0 and enforces structure on whatever entries exist; authoring the new prose entries is a docs task with no runtime impact. Deferred to keep the 1.0 apply slice within the review budget. |
| 3 | **`RuntimeBrain` construction in the OC Flow CLI path** — build a real `RuntimeBrain` in `oc_flow/cli.py` and pass it to `OCFlowRunner` when `runtime.runtime_brain_enabled` | arch-verification 7.10 | Advisory-only seam. `OCFlowRunner` already accepts a `brain` and defaults to `NullRuntimeBrain` (`oc_flow/runner.py:137`); the StateMachine governs all transitions regardless. No 1.0 behaviour depends on a live Brain in the OC Flow CLI. (Note: the runtime-scheduler Brain/estimator injection — 7.9 — *did* land in `runtime/__init__.py:410-411`.) |
| 4 | **Any remaining non-build-core B5 tooling** | spec PROD-005 Deferral Ledger | Catch-all per the baked build-core decision: only baseline + diff + ADR-section guard + surface-guard are in 1.0 scope; richer architecture-governance tooling is deferred. |

## Promotion

These items have no release gate blocking 1.0. They should be scheduled into a post-1.0 docs /
governance hardening pass. The advisory `RuntimeBrain` CLI seam (item 3) is gated behind
`runtime.runtime_brain_enabled` and can be wired whenever the advisory Brain is promoted from
advisory to load-bearing.
