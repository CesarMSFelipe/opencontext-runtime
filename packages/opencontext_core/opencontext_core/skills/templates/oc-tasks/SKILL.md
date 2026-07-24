---
name: oc-tasks
description: Tasks phase — break the design into an ordered implementation checklist.
triggers:
  - oc-tasks
  - break into tasks
  - task breakdown
version: 0.1.0
---

# oc-tasks

Slice the design into ordered, actionable work items. Run this phase **as the OC
Planner subagent**.

## When to use

After `oc-design`, before apply.

## Run as the persona

- **Task tool**, `subagent_type: oc-planner`.
- Pass the change `<slug>` and the `trace_id`; delegate the phase to it.

## Steps (the spawned subagent performs these)

1. Keep the change `trace_id`.
2. **Prime from this change's memory.** Call `opencontext_memory_context` with
   `change:<slug>` to load the design before slicing tasks.
3. Produce an ordered checklist; each task names its file paths, a short
   description, and complexity. Use `opencontext_impact` so test tasks cover the
   affected tests.
4. **Honor the session `delivery`/`chain`** when sizing the work into PRs (see
   below) — size the plan against the ~400-line review budget and mark the split
   boundary when the session's delivery strategy calls for chained/stacked PRs.
5. **Route the artifact per the session `artifact_store`** (see below) — write the
   `openspec/changes/<change-id>/tasks.md` file, `opencontext_memory_save`, both, or
   neither, according to the mode. Hand off to `oc-apply`.

## Honor the session artifact_store

Read the session's `artifact_store` from the spawn handoff
(the *"Honor the session choices: … artifact_store=…"* instruction line the
CLI/preflight emits). Route this
phase's artifact accordingly; if the value is missing/unknown, use the `hybrid`
default. Do NOT hang waiting for it.

- `hybrid` (default) — write `openspec/changes/<change-id>/tasks.md` AND
  `opencontext_memory_save` the ordered task list (`key: change:<slug>`,
  `tags: [change:<slug>]`, `layer: PROCEDURAL`).
- `openspec` — write the `openspec/changes/<change-id>/tasks.md` file only; skip the
  memory save.
- `engram` — `opencontext_memory_save` only (same key/tags/layer as `hybrid`); write
  NO openspec file.
- `none` — return the task list inline to the caller; write no file and save nothing.

## Honor the session delivery / chain strategy

Read the session's `delivery` and `chain` from the same *"Honor the session choices:
… delivery=… chain=…"* handoff line. Size and split the task plan against the
~400-line review budget accordingly; if the values are missing/unknown, use the
`ask-on-risk` + `stacked-to-main` defaults. Load the shipped **`chained-pr`** skill
(`opencontext_sdd/skills/chained-pr/SKILL.md`) and **`work-unit-commits`** skill for
the exact split/commit rules before planning any multi-PR breakdown; if that skill is
unavailable, apply the inline split rule below.

- Estimate the total changed lines. If the plan stays at/under ~400 changed lines and
  is focused, keep it a **single PR** regardless of `delivery`.
- `delivery=plan-only` or `delivery=single-pr` — do NOT chain: produce one task list /
  one PR boundary. `single-pr` over ~400 lines requires a `size:exception` note in the
  plan; `plan-only` stops at planning (no PR/apply boundary).
- `delivery=ask-on-risk` (default) — when the estimate exceeds ~400 lines or touches a
  hot path (auth/update/security/payments), flag a chained-PR recommendation and mark
  the split boundary so the orchestrator can decide before apply.
- `delivery=auto-chain` — when the estimate exceeds ~400 lines, pre-slice the plan into
  chained work units (one deliverable unit per PR, tests/docs kept with their unit).
- `delivery=exception-ok` — a single oversized PR is acceptable; record `size:exception`
  in the plan and do not force a split.
- `chain=stacked-to-main` (default) — each sliced PR targets `main` in order.
- `chain=feature-branch-chain` — child PR #1 targets the tracker/feature branch; each
  later child targets the immediate previous PR branch. Only the tracker merges to
  `main`.

## Rules

1. Tasks must be independently verifiable and ordered by dependency.
2. Pair implementation tasks with their test tasks (TDD-first).
3. No code edits in this phase.
