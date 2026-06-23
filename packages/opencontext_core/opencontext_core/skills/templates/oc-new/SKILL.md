---
name: oc-new
description: Start a new change — automatically runs the full SDD flow end to end.
triggers:
  - oc-new
  - new change
  - start a change
  - new feature
version: 0.1.0
---

# oc-new

Start a new SDD change and **drive the whole flow automatically**. This is the
single entry point: it runs every phase in order by **spawning the right persona
subagent for each phase** (Claude Code Task tool), pausing only at the approval
gate before writing code.

## When to use

At the very beginning of a change, when the developer describes a feature, bug
fix, or refactor. Prefer this over invoking each phase by hand.

## Flow (run automatically, in order)

Derive a change `<slug>` from the request and create a `trace_id`; carry both
through every phase. Each phase is **delegated to its persona via the Task tool**
(`subagent_type:` below) — the main thread sequences and gates, it does not do the
phase work itself.

1. **oc-explore** → spawn `subagent_type: oc-explorer` — map the code with
   `opencontext_context` / `opencontext_impact`; produce the verified context pack.
2. **oc-propose** → spawn `subagent_type: oc-orchestrator` — intent, scope,
   affected areas, non-goals.
3. **oc-spec** → spawn `subagent_type: oc-orchestrator` — requirements (RFC 2119) +
   GIVEN/WHEN/THEN.
4. **oc-design** → spawn `subagent_type: oc-architect` — architecture, components,
   data flow, test strategy.
5. **oc-tasks** → spawn `subagent_type: oc-orchestrator` — ordered, verifiable
   checklist (TDD-first).
6. **Approval gate** — show the plan; proceed only on approval (or `--yes`).
7. **oc-apply** → spawn `subagent_type: oc-builder` (and `subagent_type: oc-tester`
   first under strict TDD) — tests first, then implementation.
8. **oc-verify** → spawn `subagent_type: oc-reviewer` — run tests + gates in a fresh
   context.
9. **oc-archive** → spawn `subagent_type: oc-orchestrator` — persist run/memory/graph
   deltas; the KG is rebuilt with the change.

The single-process equivalent is `opencontext loop --task "<change>" --flow full`.

## Memory loop (every phase)

The change's memory is the thread between phases. Each spawned persona:

- **Primes at start** — calls `opencontext_memory_context` with `change:<slug>` to
  load the prior phases' saved findings before doing its work.
- **Saves at end** — calls `opencontext_memory_save` with `key: change:<slug>` and
  `tags: [change:<slug>]`, choosing the layer by content (SEMANTIC for facts,
  PROCEDURAL for patterns, FAILURE for errors, EPISODIC for events).

So later phases read exactly this change's memory; nothing leaks across changes.

## Rules

1. Run the phases in order without waiting for the user to invoke each one; the
   only stop is the approval gate before code is written.
2. Carry one `trace_id` and one change `<slug>` across all phases.
3. Each phase runs as its spawned persona subagent and passes its gates before the
   next begins; a failed gate stops the chain — report it, do not route around it.
4. Never write production code before the spec, design, and approval exist.
