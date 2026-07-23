---
name: oc-design
description: Design phase — the technical approach: architecture, components, data flow.
triggers:
  - oc-design
  - design the change
  - technical design
version: 0.1.0
---

# oc-design

Turn the spec into a concrete technical design. Run this phase **as the OC
Architect subagent**.

## When to use

After `oc-spec`, before tasks.

## Run as the persona

- **Task tool**, `subagent_type: oc-architect`.
- Pass the change `<slug>` and the `trace_id`; delegate the phase to it.

## Steps (the spawned subagent performs these)

1. Keep the change `trace_id`.
2. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to load the spec's requirements before designing.
3. Ground the design in the real code: `opencontext_context` for conventions,
   `opencontext_impact` for what the change affects, `opencontext_search` to reuse
   existing symbols before adding new ones.
4. Decide architecture, components, files to create/modify, data flow, and the
   testing strategy. Make trade-offs explicit; prefer the simplest design that
   meets the spec.
5. **Route the artifact per the session `artifact_store`** (see below) — write the
   `openspec/changes/<change-id>/design.md` file, `opencontext_memory_save`, both, or
   neither, according to the mode. Hand off to `oc-tasks`.

## Honor the session artifact_store

Read the session's `artifact_store` from the spawn handoff
(the *"Honor the session choices: … artifact_store=…"* instruction line the
CLI/preflight emits). Route this
phase's artifact accordingly; if the value is missing/unknown, use the `hybrid`
default. Do NOT hang waiting for it.

- `hybrid` (default) — write `openspec/changes/<change-id>/design.md` AND
  `opencontext_memory_save` the design decisions (`key: change:<slug>`,
  `tags: [change:<slug>]`, `layer: PROCEDURAL` — it is a pattern the builder must
  follow).
- `openspec` — write the `openspec/changes/<change-id>/design.md` file only; skip the
  memory save.
- `engram` — `opencontext_memory_save` only (same key/tags/layer as `hybrid`); write
  NO openspec file.
- `none` — return the design inline to the caller; write no file and save nothing.

## Rules

1. The design must let `oc-apply` implement without guessing.
2. Reuse before adding; justify every new component.
3. No code edits in this phase.
