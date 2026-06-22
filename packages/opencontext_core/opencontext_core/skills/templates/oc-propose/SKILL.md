---
name: oc-propose
description: Propose phase — turn exploration into a scoped change proposal.
triggers:
  - oc-propose
  - propose a change
  - draft a proposal
version: 0.1.0
---

# oc-propose

Turn the explore findings into a concrete proposal. Run this phase **as the OC
Orchestrator subagent**: scope and sequence, do not implement.

## When to use

After `oc-explore`, when the relevant code is understood and the change needs a
written intent + scope before a spec.

## Run as the persona

- **Task tool**, `subagent_type: oc-orchestrator`.
- Pass the change `<slug>` and the `trace_id`; delegate the phase to it.

## Steps (the spawned subagent performs these)

1. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to load the explore findings before proposing.
2. Read the explore context pack and `trace_id`; keep the same `trace_id`.
3. State the problem, the proposed approach, the affected areas (from
   `opencontext_impact`), and what is explicitly out of scope.
4. Write the proposal under `openspec/changes/<change-id>/proposal.md`.
5. **Save the proposal decisions.** Call `opencontext_memory_save` with the chosen
   approach and non-goals, `key: change:<slug>`, `tags: [change:<slug>]`,
   `layer: SEMANTIC`.
6. Hand off to `oc-spec`.

## Rules

1. No production code edits in this phase.
2. Ground the affected-areas list in the knowledge graph, not assumptions.
3. Keep scope tight; name non-goals explicitly.
