---
name: oc-spec
description: Spec phase — write the delta specification (requirements + scenarios).
triggers:
  - oc-spec
  - write the spec
  - requirements
version: 0.1.0
---

# oc-spec

Capture WHAT the change must do. Run this phase **as the OC Orchestrator
subagent**.

## When to use

After `oc-propose` is approved, before design.

## Run as the persona

- **Task tool**, `subagent_type: oc-orchestrator`.
- Pass the change `<slug>` and the `trace_id`; delegate the phase to it.

## Steps (the spawned subagent performs these)

1. Keep the change `trace_id`.
2. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to load the proposal's intent and scope before writing the spec.
3. Write requirements with RFC 2119 keywords (MUST/SHALL/SHOULD) and
   GIVEN/WHEN/THEN scenarios.
4. Save the delta spec under `openspec/changes/<change-id>/spec.md`.
5. **Save the requirements summary.** Call `opencontext_memory_save` with the key
   requirements/scenarios, `key: change:<slug>`, `tags: [change:<slug>]`,
   `layer: SEMANTIC`.
6. Hand off to `oc-design`.

## Rules

1. Specify behavior, not implementation — the HOW is the design phase.
2. Every requirement must be testable; pair it with at least one scenario.
3. No code edits in this phase.
