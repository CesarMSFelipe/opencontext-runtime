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
and close out the cycle. Run this phase **as the OC Orchestrator subagent** — it
owns sequencing and persistence. (Archive is not a harness driver phase, so it has
no `PHASE_PERSONAS` entry; the Orchestrator drives it.)

## When to use

Use after `oc-verify` passes and the change is complete.

## Run as the persona

- **Task tool**, `subagent_type: oc-orchestrator`.
- Pass the change `<slug>` and the `trace_id`; delegate the close-out to it.

## Steps (the spawned subagent performs these)

1. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to gather every phase's saved decisions before persisting.
2. Confirm the change is verified and its `trace_id` resolves to a loadable
   trace.
3. Persist memory and knowledge-graph deltas from the change: call
   `opencontext_memory_save` with the durable decisions, conventions, and gotchas,
   `key: change:<slug>`, `tags: [change:<slug>]`, choosing the layer per fact
   (SEMANTIC for facts, PROCEDURAL for patterns/conventions, FAILURE for gotchas,
   EPISODIC for the archive event).
4. Sync the change's spec into the canonical specs and mark the change archived.
5. Write the final artifact under `.opencontext/runs/<run_id>/artifacts/`.

## Rules

1. The archive phase MUST persist memory and graph deltas.
2. Every phase, including archive, must carry a `trace_id` and an artifact.
3. Do not archive an unverified change.
