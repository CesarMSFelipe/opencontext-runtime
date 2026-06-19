---
name: oc-tasks
description: Tasks phase — break the design into an ordered implementation checklist.
triggers:
  - oc-tasks
  - break into tasks
  - task breakdown
version: 0.1.0
---

# oc-tasks

Slice the design into ordered, actionable work items. Adopt the **OC Orchestrator**
persona.

## When to use

After `oc-design`, before apply.

## Steps

1. Keep the change `trace_id`.
2. Produce an ordered checklist; each task names its file paths, a short
   description, and complexity. Use `opencontext_impact` so test tasks cover the
   affected tests.
3. Save under `openspec/changes/<change-id>/tasks.md`; hand off to `oc-apply`.

## Rules

1. Tasks must be independently verifiable and ordered by dependency.
2. Pair implementation tasks with their test tasks (TDD-first).
3. No code edits in this phase.
