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

Turn the explore findings into a concrete proposal. Run this phase **as the OC
Orchestrator subagent**: scope and sequence, do not implement.

## When to use

After `oc-explore`, when the relevant code is understood and the change needs a
written intent + scope before a spec.

## Run as the persona

- **Task tool**, `subagent_type: oc-orchestrator`.
- Pass the change `<slug>` and the `trace_id`; delegate the phase to it.

## Steps (the spawned subagent performs these)

1. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to load the explore findings before proposing.
2. Read the explore context pack and `trace_id`; keep the same `trace_id`.
3. **Run the proposal question round** (see below) BEFORE writing anything. Do not
   silently decide the proposal is "clear enough" — shape it with the user through
   predefined-option product questions, then confirm the assumptions.
4. State the problem, the proposed approach, the affected areas (from
   `opencontext_impact`), and what is explicitly out of scope.
5. **Route the artifact per the session `artifact_store`** (see below) — write the
   `openspec/changes/<change-id>/proposal.md` file, `opencontext_memory_save`, both, or
   neither, according to the mode.
6. Hand off to `oc-spec`.

## Honor the session artifact_store

Read the session's `artifact_store` from the spawn handoff
(the *"Honor the session choices: … artifact_store=…"* instruction line the
CLI/preflight emits). Route this
phase's artifact accordingly; if the value is missing/unknown, use the `hybrid`
default. Do NOT hang waiting for it.

- `hybrid` (default) — write `openspec/changes/<change-id>/proposal.md` AND
  `opencontext_memory_save` the chosen approach and non-goals (`key: change:<slug>`,
  `tags: [change:<slug>]`, `layer: SEMANTIC`).
- `openspec` — write the `openspec/changes/<change-id>/proposal.md` file only; skip the
  memory save.
- `engram` — `opencontext_memory_save` only (same key/tags/layer as `hybrid`); write
  NO openspec file.
- `none` — return the proposal inline to the caller; write no file and save nothing.
  The `## Proposal question round` non-interactive fallback below still applies to the
  inline artifact.

## Proposal question round (do this BEFORE writing the proposal)

Improve the PRD/proposal by uncovering business understanding, business rules,
implications, impact, edge cases, and product tradeoffs — not harness mechanics.

- Ask **3–5 concrete PRODUCT questions** in one round, each as a **predefined-option
  question** (offer 3–4 labelled choices per question; a free-text "Something else"
  only as the LAST option). The change task/idea string is the sole free-text input
  — every other decision is a selection. Cover the smallest useful subset of:
  1. **business problem** — what pain / opportunity / cost makes this worth doing now;
  2. **target users & situations** — who is affected, in which workflow, at what moment;
  3. **business rules** — policies, permissions, thresholds, lifecycle, compliance,
     or domain invariants the proposal must respect;
  4. **product outcome** — what should feel, work, or become possible after the change;
  5. **implications & impact** — which teams, workflows, data, UX, or support burden
     may be affected;
  6. **edge cases** — empty states, partial data, failures, permissions, migration
     states, unusual customers, conflicting needs;
  7. **non-goals / first-slice scope** — what belongs in the first slice, what is
     later refinement, what must stay unchanged.
- After the answers, **SUMMARIZE the resulting proposal assumptions** and ask a single
  **predefined-option** selector: **accept** (proceed) / **revise** (correct an
  assumption) / **second round** (ask another 3–5 questions). Do NOT ask about test
  commands, PR shape, changed-line budget, or other delivery mechanics at proposal
  time unless the user explicitly asks to discuss delivery.
- **Non-interactive / blocked / CI fallback** — if you cannot ask the user directly
  (no TTY, non-interactive, or a blocked host), do NOT hang. Write a
  `## Proposal question round` section into the proposal artifact containing the
  questions you would have asked and the assumptions you are proceeding on, then
  continue. The proposal always gets written.
- **Language contract** — you may ask the questions in the user's language, but the
  proposal artifact (and its `## Proposal question round` fallback section) stays in
  neutral, professional English. Never inject regional voice, slang, or exclamations
  into the artifact.

## Rules

1. No production code edits in this phase.
2. Ground the affected-areas list in the knowledge graph, not assumptions.
3. Keep scope tight; name non-goals explicitly.
