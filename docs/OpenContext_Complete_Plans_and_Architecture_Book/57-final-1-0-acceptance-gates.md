# 57 — Final 1.0 Acceptance Gates

Authority: `OC-FINAL-CONVERGENCE-001.md` §7.5 + §10 + §11. The exact, machine-checkable gates
that must ALL pass before OpenContext is declared 1.0. Owned by PR-017; enforced in CI.

## A. Mandatory benchmark gates (convergence §6 PR-017)

| Gate | Pass condition | Source |
|------|----------------|--------|
| first-run | init→doctor→index→run sequence succeeds on fixture | doc 56 |
| oc-flow-localized-bugfix | OC Flow fixes a seeded failing test within token + attempt budget | PR-007 |
| sdd-formal-feature | SDD completes a small feature end-to-end with all phase outputs | PR-004 |
| context-token-efficiency | token use ≤ baseline; claim-free, parity-gated (no strawman) | PR-010/011 |
| kg-retrieval-precision | R@5 / MRR ≥ baseline on retrieval fixtures | PR-008 |
| memory-usefulness | promoted memory improves a repeat run; gate K-5 holds | PR-009 |
| policy-security | no forbidden-path write, no secret leak, redaction verified | PR-005/012 |
| plugin-compatibility | sample plugins load/validate against public contracts | PR-015 |
| provider-fallback | provider error/timeout → fallback path exercised | PR-012 |
| resume-rollback | interrupt→resume restores state; bad mutation→rollback restores files | PR-002 |

## B. Functional 1.0 gate (convergence §10) — the run must reliably

1. create usable config; 2. detect capabilities; 3. build/init KG; 4. select OC Flow for
localized bugfix; 5. select SDD for formal/high-risk; 6. retrieve minimal context; 7. apply small
mutation safely; 8. run local inspection; 9. diagnose bounded failures; 10. escalate when needed;
11. persist artifacts + receipts; 12. report cost/confidence; 13. update memory/KG at
consolidation; 14. give actionable summary; 15. resume if interrupted.

Any failure ⇒ not 1.0-ready.

## C. Regression / non-negotiable gates

- No regression in first-run success rate.
- No regression in benchmark quality.
- No uncontrolled token increase.
- No critical policy bypass.
- Existing suite stays green (currently ~2700+ tests); `scripts/gate_k.sh` 12/12.
- mypy strict clean; ruff clean; forbidden-names clean.
- Benchmark methodology is **versioned**; a regression **blocks release**.
- `publish.yml` uses `secrets.PYPI_API_TOKEN` (not OIDC) — recurring break, must stay fixed.

## D. Governance gates

- Every requirement in `54-requirement-to-pr-traceability-matrix.md` is MET, explicitly DEFERRED
  to 1.x with reason, or rejected with rationale. No orphans.
- Every important runtime decision/action is reconstructable from artifacts + receipts (§9.14).
- Owner-resolution hooks exist (§9.17) even if full Organization Graph is 1.x.

## Verdict rule

1.0 is declared only when **A (all 10) ∧ B (all 15) ∧ C ∧ D** hold in a single CI run on `main`.
Until then the product is pre-1.0 regardless of feature count.
