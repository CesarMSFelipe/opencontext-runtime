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

Turn the explore findings into a concrete proposal. Adopt the **OC Orchestrator**
persona: scope and sequence, do not implement.

## When to use

After `oc-explore`, when the relevant code is understood and the change needs a
written intent + scope before a spec.

## Steps

1. Read the explore context pack and `trace_id`; keep the same `trace_id`.
2. State the problem, the proposed approach, the affected areas (from
   `opencontext_impact`), and what is explicitly out of scope.
3. Write the proposal under `openspec/changes/<change-id>/proposal.md`.
4. Hand off to `oc-spec`.

## Rules

1. No production code edits in this phase.
2. Ground the affected-areas list in the knowledge graph, not assumptions.
3. Keep scope tight; name non-goals explicitly.
