---
name: oc-verify
description: Validate that the implementation matches the spec, design, and tasks.
triggers:
  - oc-verify
  - verify change
  - validate implementation
  - check the work
version: 0.1.0
---

# oc-verify

Validate that an applied SDD change matches its spec, design, and task list, and
that the project's health checks pass.

## When to use

Use after `oc-apply` completes, before archiving the change.

## Steps

1. Re-read the change's spec/design/tasks and confirm each task is satisfied.
2. Run the test suite and `opencontext verify` for a health check.
3. Use `opencontext_impact` to confirm no unexpected blast radius.
4. Record verification results against the change's `trace_id`.
5. If gaps are found, hand back to `oc-apply`; otherwise hand off to
   `oc-archive`.

## Rules

1. Do not mark a change verified while any task is unmet or tests fail.
2. Surface security/governance gate failures explicitly — never swallow them.
3. Keep the verification trace loadable and attributable.
