---
name: oc-apply
description: Implement SDD tasks — writes code following the approved spec and design.
triggers:
  - oc-apply
  - apply change
  - implement tasks
  - write the code
version: 0.1.0
---

# oc-apply

Implement the tasks for an approved SDD change. Run this phase **as the OC Builder
subagent** (with the OC Tester for the failing tests under TDD). It writes code
that follows the spec and design, respecting the configured TDD mode and token
budgets.

## When to use

Use after a proposal/spec/design exists and the tasks are ready to implement.

## Run as the persona

- **Task tool**, `subagent_type: oc-builder` — delegate the implementation to it.
- Under `strict` TDD, first spawn **Task tool**, `subagent_type: oc-tester` to
  write the failing tests, then hand to `oc-builder` to make them pass.
- Pass the change `<slug>` and the `trace_id` to each.

## Steps (the spawned subagent performs these)

1. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to load the design decisions and task plan before editing.
2. Load the change's spec, design, and tasks from `openspec/changes/<change-id>/`.
3. Preserve the `trace_id` from the proposal phase.
4. Respect the configured TDD mode:
   - `strict` — write a failing test BEFORE the implementation.
   - `ask` — ask the developer before skipping tests.
   - `off` — code-first is allowed.
5. **Honor the session `delivery`/`chain`** when splitting the implementation into
   PRs (see below) — implement within the PR boundary the session's delivery
   strategy set, using work-unit commits and the ~400-line review budget.
6. Make surgical edits scoped to the current task; use `opencontext_impact`
   before touching shared symbols.
7. Write artifacts to `.opencontext/runs/<run_id>/artifacts/`.
8. **Save what was implemented.** Call `opencontext_memory_save` with the edits made
   and any pattern worth reusing, `key: change:<slug>`, `tags: [change:<slug>]`,
   `layer: PROCEDURAL` (use FAILURE for a test/gate that failed and how it was
   fixed).
9. Hand off to `oc-verify` once the tasks are implemented.

## Honor the session delivery / chain strategy

Read the session's `delivery` and `chain` from the spawn handoff
(the *"Honor the session choices: … delivery=… chain=…"* instruction line the
CLI/preflight emits). Split the implementation into PRs accordingly; if the values
are missing/unknown, use
the `ask-on-risk` + `stacked-to-main` defaults. Do NOT hang waiting for them. Load the
shipped **`chained-pr`** skill (`opencontext_sdd/skills/chained-pr/SKILL.md`) and
**`work-unit-commits`** skill for the exact split/commit rules before creating any
multi-PR breakdown; if that skill is unavailable, apply the inline rule below.

- Keep the change a **single PR** when it stays at/under ~400 changed lines and is
  focused, regardless of `delivery`. Use one work-unit commit per task; each commit
  leaves the suite green.
- `delivery=plan-only` or `delivery=single-pr` — do NOT chain: land one PR.
  `single-pr` over ~400 lines proceeds only with a recorded `size:exception`.
- `delivery=ask-on-risk` (default) — if the work exceeds ~400 lines or touches a hot
  path (auth/update/security/payments), STOP at the split boundary and surface the
  chained-PR recommendation to the orchestrator instead of landing one oversized PR.
- `delivery=auto-chain` — implement only the next autonomous slice as one PR (clear
  start/finish/verification/rollback boundary), then hand back for the next slice.
- `delivery=exception-ok` — a single oversized PR is acceptable this run; proceed under
  `size:exception`.
- `chain=stacked-to-main` (default) — each sliced PR targets `main` in order.
- `chain=feature-branch-chain` — child PR #1 targets the tracker/feature branch; each
  later child targets the immediate previous PR branch; only the tracker merges to
  `main`.

## Rules

1. Honor approval gates — do not bypass write approval.
2. Do not disable security redaction or enable external providers.
3. Keep each edit minimal and correct; no gold-plating.
