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
5. Make surgical edits scoped to the current task; use `opencontext_impact`
   before touching shared symbols.
6. Write artifacts to `.opencontext/runs/<run_id>/artifacts/`.
7. **Save what was implemented.** Call `opencontext_memory_save` with the edits made
   and any pattern worth reusing, `key: change:<slug>`, `tags: [change:<slug>]`,
   `layer: PROCEDURAL` (use FAILURE for a test/gate that failed and how it was
   fixed).
8. Hand off to `oc-verify` once the tasks are implemented.

## Rules

1. Honor approval gates — do not bypass write approval.
2. Do not disable security redaction or enable external providers.
3. Keep each edit minimal and correct; no gold-plating.
