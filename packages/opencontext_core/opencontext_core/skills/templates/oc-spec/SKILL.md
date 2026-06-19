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

Capture WHAT the change must do. Adopt the **OC Orchestrator** persona.

## When to use

After `oc-propose` is approved, before design.

## Steps

1. Keep the change `trace_id`.
2. Write requirements with RFC 2119 keywords (MUST/SHALL/SHOULD) and
   GIVEN/WHEN/THEN scenarios.
3. Save the delta spec under `openspec/changes/<change-id>/spec.md`.
4. Hand off to `oc-design`.

## Rules

1. Specify behavior, not implementation — the HOW is the design phase.
2. Every requirement must be testable; pair it with at least one scenario.
3. No code edits in this phase.
