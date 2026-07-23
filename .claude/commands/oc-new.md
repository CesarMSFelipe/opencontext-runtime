---
description: Start a new SDD change — runs the full flow automatically
---

Start a new spec-driven change and drive the whole flow in order by SPAWNING each phase's persona subagent with the Task tool (the main thread sequences and gates, it does not do the work):
explore -> `subagent_type: oc-explorer`; propose -> `subagent_type: oc-orchestrator`; spec -> `subagent_type: oc-requirements`; tasks -> `subagent_type: oc-planner`; design -> `subagent_type: oc-architect`; approval gate; apply (tests first) -> `subagent_type: oc-tester` then `subagent_type: oc-builder`; verify -> `subagent_type: oc-harness-verifier`; archive -> `subagent_type: oc-archivist`.
Memory loop every phase: derive a change `<slug>`; each persona PRIMES at start with `opencontext_memory_context` for `change:<slug>` and SAVES at end with `opencontext_memory_save` (`key`/`tags` = `change:<slug>`; layer SEMANTIC for facts, PROCEDURAL for patterns, FAILURE for errors).
Build context with `opencontext_context` and check `opencontext_impact` before any edit; pause for approval before writing code.
Session preflight FIRST (once): if the handoff carries `session_choices`, honor them; else ASK four predefined-option groups (execution mode interactive/automatic, artifact store hybrid/openspec/engram/none, delivery ask-on-risk/single-pr/auto-chain/exception-ok/plan-only, chain stacked-to-main/feature-branch-chain), each guided (recommend + effect + safe default), cached for the session — non-interactive falls back to safe defaults, never hangs. In `interactive` mode, pause after each phase: summarize, then ask proceed/adjust/stop (phase-scoped).
The `oc-propose` phase runs a proposal question round (3 to 5 predefined-option product questions, then accept/revise/second-round) before writing the proposal; non-interactive writes a `## Proposal question round` section instead of hanging.

Change: $ARGUMENTS
