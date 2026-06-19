---
name: oc-explore
description: Explore phase — map the codebase for a change before proposing anything.
triggers:
  - oc-explore
  - explore the code
  - investigate
  - map the codebase
version: 0.1.0
---

# oc-explore

Investigate the territory before any change. Adopt the **OC Explorer** persona:
map, do not modify.

## When to use

First phase of a change, or any time you need a grounded picture of what the task
touches before proposing or designing.

## Steps

1. Build a context pack: `opencontext pack . --query "<task>" --max-tokens 3000 --mode plan`.
2. Locate symbols with `opencontext_search` / `opencontext_context`; trace flow with
   `opencontext_callers` / `opencontext_callees`.
3. Bound the blast radius with `opencontext_impact`.
4. Report what exists, what's relevant, and what's risky — with file:line evidence.
   Surface unknowns explicitly.

## Rules

1. Read-only — never propose or edit code in this phase.
2. Prefer verified evidence over guesses; cite file:line.
3. Produce the minimal context the later phases need; omit the rest.
