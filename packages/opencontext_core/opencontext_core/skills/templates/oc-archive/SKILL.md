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
and close out the cycle.

## When to use

Use after `oc-verify` passes and the change is complete.

## Steps

1. Confirm the change is verified and its `trace_id` resolves to a loadable
   trace.
2. Persist memory deltas (decisions, conventions, gotchas) and knowledge-graph
   deltas from the change.
3. Sync the change's spec into the canonical specs and mark the change archived.
4. Write the final artifact under `.opencontext/runs/<run_id>/artifacts/`.

## Rules

1. The archive phase MUST persist memory and graph deltas.
2. Every phase, including archive, must carry a `trace_id` and an artifact.
3. Do not archive an unverified change.
