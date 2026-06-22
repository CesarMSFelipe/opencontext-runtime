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

Slice the design into ordered, actionable work items. Run this phase **as the OC
Orchestrator subagent**.

## When to use

After `oc-design`, before apply.

## Run as the persona

- **Task tool**, `subagent_type: oc-orchestrator`.
- Pass the change `<slug>` and the `trace_id`; delegate the phase to it.

## Steps (the spawned subagent performs these)

1. Keep the change `trace_id`.
2. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to load the design before slicing tasks.
3. Produce an ordered checklist; each task names its file paths, a short
   description, and complexity. Use `opencontext_impact` so test tasks cover the
   affected tests.
4. Save under `openspec/changes/<change-id>/tasks.md`.
5. **Save the task plan.** Call `opencontext_memory_save` with the ordered task
   list, `key: change:<slug>`, `tags: [change:<slug>]`, `layer: PROCEDURAL`. Hand
   off to `oc-apply`.

## Rules

1. Tasks must be independently verifiable and ordered by dependency.
2. Pair implementation tasks with their test tasks (TDD-first).
3. No code edits in this phase.
