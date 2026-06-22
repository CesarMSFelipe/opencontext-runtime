---
description: Start a new SDD change — runs the full flow automatically
---

Start a new spec-driven change and drive the whole flow in order by SPAWNING each phase's persona subagent with the Task tool (the main thread sequences and gates, it does not do the work):
explore -> `subagent_type: oc-explorer`; propose/spec/tasks -> `subagent_type: oc-orchestrator`; design -> `subagent_type: oc-architect`; approval gate; apply (tests first) -> `subagent_type: oc-tester` then `subagent_type: oc-builder`; verify -> `subagent_type: oc-reviewer`; archive -> `subagent_type: oc-orchestrator`.
Memory loop every phase: derive a change `<slug>`; each persona PRIMES at start with `opencontext_memory_context` for `change:<slug>` and SAVES at end with `opencontext_memory_save` (`key`/`tags` = `change:<slug>`; layer SEMANTIC for facts, PROCEDURAL for patterns, FAILURE for errors).
Build context with `opencontext_context` and check `opencontext_impact` before any edit; pause for approval before writing code.

Change: $ARGUMENTS
