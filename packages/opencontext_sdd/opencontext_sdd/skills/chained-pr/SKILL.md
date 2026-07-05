---
name: chained-pr
description: "Trigger: PRs over 400 lines, stacked PRs, review slices. Split oversized changes into chained PRs that protect review focus."
license: Apache-2.0
metadata:
  author: opencontext-runtime
  version: "1.0"
---

## Activation Contract

Load this skill when a planned PR may exceed **400 changed lines**, SDD forecasts high, or the user asks for chained/stacked PRs or review slices.

## Hard Rules

- Split PRs over **400 changed lines** unless a maintainer explicitly accepts `size:exception`.
- Keep each PR reviewable in about **≤60 minutes**.
- Use one deliverable work unit per PR; keep tests/docs with the unit they verify.
- Every child PR must include a dependency diagram marking the current PR with `📍`.
- In Feature Branch Chain, child PR #1 targets the tracker branch, later children target the immediate parent branch.

## Decision Gates

| Condition | Action |
|---|---|
| PR ≤400 changed lines and focused | Keep single PR |
| PR >400, each slice can land independently | Use Stacked PRs to main |
| PR >400, feature must integrate before main | Use Feature Branch Chain with tracker |

## Execution Steps

1. Estimate changed lines and identify independent work units.
2. Choose strategy: stacked-to-main or feature-branch-chain.
3. Create branches/PRs using the chosen strategy only.
4. Add Chain Context to each PR without replacing the repo PR template.
5. Verify each PR independently.

## References

- [references/chaining-details.md](references/chaining-details.md) — strategy diagrams, commands, reviewer guidance.
