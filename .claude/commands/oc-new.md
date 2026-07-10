---
description: Start a new SDD change — runs the full flow automatically
---

Start a new spec-driven change and drive the whole flow in order by SPAWNING each phase's persona subagent with the Task tool (the main thread sequences and gates, it does not do the work):
explore -> `subagent_type: oc-explorer`; propose -> `subagent_type: oc-orchestrator`; spec -> `subagent_type: oc-requirements`; tasks -> `subagent_type: oc-planner`; design -> `subagent_type: oc-architect`; approval gate; apply (tests first) -> `subagent_type: oc-tester` then `subagent_type: oc-builder`; verify -> `subagent_type: oc-harness-verifier`; archive -> `subagent_type: oc-archivist`.
Memory loop every phase: derive a change `<slug>`; each persona PRIMES at start with `opencontext_memory_context` for `change:<slug>` and SAVES at end with `opencontext_memory_save` (`key`/`tags` = `change:<slug>`; layer SEMANTIC for facts, PROCEDURAL for patterns, FAILURE for errors).
Build context with `opencontext_context` and check `opencontext_impact` before any edit; pause for approval before writing code. Present the approval gate (and any ambiguous/scope/design decision) as an option-question — selectable options plus a custom/'Other' choice, using `AskUserQuestion` when the host provides it, else letter/number options — never a single exact free-text reply.

Change: $ARGUMENTS
