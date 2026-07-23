---
name: oc-archive
description: Archive a completed SDD change — syncs specs and closes the cycle.
triggers:
  - oc-archive
  - archive change
  - close the cycle
  - finish change
version: 0.1.0
---

# oc-archive

Archive a verified SDD change: persist memory and graph deltas, sync the specs,
and close out the cycle. Run this phase **as the OC Archivist subagent** — it
owns the memory harvest and receipt writing.

## When to use

Use after `oc-verify` passes and the change is complete.

## Run as the persona

- **Task tool**, `subagent_type: oc-archivist`.
- Pass the change `<slug>` and the `trace_id`; delegate the close-out to it.

## Steps (the spawned subagent performs these)

1. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to gather every phase's saved decisions before persisting.
2. Confirm the change is verified and its `trace_id` resolves to a loadable
   trace.
3. **Route the archive artifact per the session `artifact_store`** (see below):
   persist the durable memory, sync the spec files, both, or neither, according to the
   mode.
4. Write the final archive artifact under `.opencontext/runs/<run_id>/artifacts/`
   (the run receipt is always written regardless of `artifact_store`).

## Honor the session artifact_store

Read the session's `artifact_store` from the spawn handoff
(the *"Honor the session choices: … artifact_store=…"* instruction line the
CLI/preflight emits). Route the
archive artifact accordingly; if the value is missing/unknown, use the `hybrid`
default. Do NOT hang waiting for it. The `.opencontext/runs/<run_id>/artifacts/`
receipt above is the run trace and is always written; this routing governs the
durable archive artifact (memory harvest + `openspec/` spec sync).

- `hybrid` (default) — sync the change's spec into the canonical
  `openspec/` specs AND `opencontext_memory_save` the durable decisions, conventions,
  and gotchas (`key: change:<slug>`, `tags: [change:<slug>]`, choosing the layer per
  fact: SEMANTIC for facts, PROCEDURAL for patterns/conventions, FAILURE for gotchas,
  EPISODIC for the archive event).
- `openspec` — sync the spec into the canonical `openspec/` specs and mark the change
  archived; skip the memory save.
- `engram` — `opencontext_memory_save` only (same key/tags/layers as `hybrid`); write
  NO openspec spec-sync file.
- `none` — report the archive summary inline; write no openspec file and save nothing
  durable (only the run receipt above).

## Rules

1. The archive phase MUST persist the change's durable outcome via the active
   `artifact_store` (memory and/or graph deltas per the mode).
2. Every phase, including archive, must carry a `trace_id` and an artifact.
3. Do not archive an unverified change.
