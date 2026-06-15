---
name: sdd-new
description: Start a new Spec-Driven Development change — runs exploration then creates a proposal.
triggers:
  - sdd-new
  - new change
  - start a change
  - new feature
version: 0.1.0
---

# sdd-new

Start a new SDD change. This skill kicks off the spec-driven workflow by
exploring the codebase with the OpenContext knowledge graph and drafting a
proposal before any code is written.

## When to use

Use at the very beginning of a change, when the developer describes a feature,
bug fix, or refactor and wants a structured plan rather than ad-hoc edits.

## Steps

1. Build a context pack for the change:
   `opencontext pack . --query "<change description>" --max-tokens 3000 --mode plan`.
2. Use `opencontext_context` / `opencontext_search` to locate the relevant
   symbols and `opencontext_impact` to estimate blast radius.
3. Record a `trace_id` and preserve it across every later phase.
4. Draft a proposal under `openspec/changes/<change-id>/` capturing the problem,
   the approach, and the affected areas.
5. Hand off to `sdd-apply` once the proposal is approved.

## Rules

1. Do NOT dump the full repository — rely on context packs.
2. Always produce a `trace_id` and a proposal artifact.
3. Never edit production code in this phase; this is explore + propose only.
