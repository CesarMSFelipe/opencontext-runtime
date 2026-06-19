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

Turn the spec into a concrete technical design. Adopt the **OC Architect** persona.

## When to use

After `oc-spec`, before tasks.

## Steps

1. Keep the change `trace_id`.
2. Ground the design in the real code: `opencontext_context` for conventions,
   `opencontext_impact` for what the change affects, `opencontext_search` to reuse
   existing symbols before adding new ones.
3. Decide architecture, components, files to create/modify, data flow, and the
   testing strategy. Make trade-offs explicit; prefer the simplest design that
   meets the spec.
4. Save under `openspec/changes/<change-id>/design.md`; hand off to `oc-tasks`.

## Rules

1. The design must let `oc-apply` implement without guessing.
2. Reuse before adding; justify every new component.
3. No code edits in this phase.
