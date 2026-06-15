---
name: sdd-apply
description: Implement SDD tasks — writes code following the approved spec and design.
triggers:
  - sdd-apply
  - apply change
  - implement tasks
  - write the code
version: 0.1.0
---

# sdd-apply

Implement the tasks for an approved SDD change. This skill writes code that
follows the spec and design, respecting the configured TDD mode and token
budgets.

## When to use

Use after a proposal/spec/design exists and the tasks are ready to implement.

## Steps

1. Load the change's spec, design, and tasks from `openspec/changes/<change-id>/`.
2. Preserve the `trace_id` from the proposal phase.
3. Respect the configured TDD mode:
   - `strict` — write a failing test BEFORE the implementation.
   - `ask` — ask the developer before skipping tests.
   - `off` — code-first is allowed.
4. Make surgical edits scoped to the current task; use `opencontext_impact`
   before touching shared symbols.
5. Write artifacts to `.opencontext/runs/<run_id>/artifacts/`.
6. Hand off to `sdd-verify` once the tasks are implemented.

## Rules

1. Honor approval gates — do not bypass write approval.
2. Do not disable security redaction or enable external providers.
3. Keep each edit minimal and correct; no gold-plating.
