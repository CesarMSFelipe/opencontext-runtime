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
that the project's health checks pass. Run this phase **as the OC Reviewer
subagent** — a fresh context, not the one that wrote the code.

## When to use

Use after `oc-apply` completes, before archiving the change.

## Run as the persona

- **Task tool**, `subagent_type: oc-reviewer` — delegate the review to a fresh
  context so it does not rubber-stamp its own work.
- Pass the change `<slug>` and the `trace_id`.

## Steps (the spawned subagent performs these)

1. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to load the spec, design, and what apply implemented.
2. Re-read the change's spec/design/tasks and confirm each task is satisfied.
3. Run the test suite and `opencontext verify` for a health check.
4. Use `opencontext_impact` to confirm no unexpected blast radius.
5. Record verification results against the change's `trace_id`.
6. **Save the verdict.** Call `opencontext_memory_save` with the result and any gap
   found, `key: change:<slug>`, `tags: [change:<slug>]`, `layer: EPISODIC` for the
   verification event (FAILURE for a gap handed back to apply).
7. If gaps are found, hand back to `oc-apply`; otherwise hand off to
   `oc-archive`.

## Rules

1. Do not mark a change verified while any task is unmet or tests fail.
2. Surface security/governance gate failures explicitly — never swallow them.
3. Keep the verification trace loadable and attributable.
