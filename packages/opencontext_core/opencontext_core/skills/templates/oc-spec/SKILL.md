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

Capture WHAT the change must do. Run this phase **as the OC Requirements
subagent**.

## When to use

After `oc-propose` is approved, before design.

## Run as the persona

- **Task tool**, `subagent_type: oc-requirements`.
- Pass the change `<slug>` and the `trace_id`; delegate the phase to it.

## Steps (the spawned subagent performs these)

1. Keep the change `trace_id`.
2. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to load the proposal's intent and scope before writing the spec.
3. Write requirements with RFC 2119 keywords (MUST/SHALL/SHOULD) and
   GIVEN/WHEN/THEN scenarios.
4. **Route the artifact per the session `artifact_store`** (see below) — write the
   `openspec/changes/<change-id>/spec.md` file, `opencontext_memory_save`, both, or
   neither, according to the mode.
5. Hand off to `oc-design`.

## Honor the session artifact_store

Read the session's `artifact_store` from the spawn handoff
(the *"Honor the session choices: … artifact_store=…"* instruction line the
CLI/preflight emits). Route this
phase's artifact accordingly; if the value is missing/unknown, use the `hybrid`
default. Do NOT hang waiting for it.

- `hybrid` (default) — write `openspec/changes/<change-id>/spec.md` AND
  `opencontext_memory_save` the requirements summary (`key: change:<slug>`,
  `tags: [change:<slug>]`, `layer: SEMANTIC`).
- `openspec` — write the `openspec/changes/<change-id>/spec.md` file only; skip the
  memory save.
- `engram` — `opencontext_memory_save` only (same key/tags/layer as `hybrid`); write
  NO openspec file.
- `none` — return the spec inline to the caller; write no file and save nothing.

## Rules

1. Specify behavior, not implementation — the HOW is the design phase.
2. Every requirement must be testable; pair it with at least one scenario.
3. No code edits in this phase.
