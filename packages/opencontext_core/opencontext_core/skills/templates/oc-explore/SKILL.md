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

Investigate the territory before any change. Run this phase **as the OC Explorer
subagent**: spawn it and delegate the work — map, do not modify.

## When to use

First phase of a change, or any time you need a grounded picture of what the task
touches before proposing or designing.

## Run as the persona

Spawn the persona subagent and hand the phase to it — do not do the work in the
main thread:

- **Task tool**, `subagent_type: oc-explorer`.
- Pass the task, the change `<slug>`, and the `trace_id`.

## Steps (the spawned subagent performs these)

1. **Prime from this change's memory.** Call `opencontext_memory_context` with the
   task plus `change:<slug>` to load any prior findings for this change before
   reading code.
2. Build a context pack: `opencontext pack . --query "<task>" --max-tokens 3000 --mode plan`.
3. Locate symbols with `opencontext_search` / `opencontext_context`; trace flow with
   `opencontext_callers` / `opencontext_callees`.
4. Bound the blast radius with `opencontext_impact`.
5. Report what exists, what's relevant, and what's risky — with file:line evidence.
   Surface unknowns explicitly.
6. **Save the findings.** Call `opencontext_memory_save` with the map and risks,
   `key: change:<slug>` and `tags: [change:<slug>]`, `layer: SEMANTIC` for durable
   facts about the code (use FAILURE for any dead-end you hit), so the next phase
   primes from it.

## Rules

1. Read-only — never propose or edit code in this phase.
2. Prefer verified evidence over guesses; cite file:line.
3. Produce the minimal context the later phases need; omit the rest.
