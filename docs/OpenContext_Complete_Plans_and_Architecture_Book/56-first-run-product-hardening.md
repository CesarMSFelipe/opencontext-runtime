# 56 — First-Run Product Hardening

Authority: `OC-FINAL-CONVERGENCE-001.md` §7.4 + §10. Hardening plan for the exact first-run
sequence. This is the experience that decides whether OpenContext is adopted.

## Target sequence

```bash
opencontext init --profile balanced
opencontext doctor
opencontext index
opencontext run "Fix failing test" --workflow auto
```

## Per-command hardening contract

### `init --profile balanced`
- Detect project type; write `opencontext.yaml` v2; never overwrite without backup (existing
  install config-stomp bug is a regression to guard).
- No interrogation loop; sensible defaults; non-TTY safe (menu loops must guard or they hang).
- Output: what was created, chosen profile + why, next command.

### `doctor`
- Build Capability Graph (PR-000.2): languages, test runner, linter, typecheck, git, CODEOWNERS,
  provider/sampling, KG status.
- Every missing capability → one actionable line (how to enable / what degrades).
- Exit non-zero only on hard blockers; degrade gracefully otherwise.

### `index`
- Build KG v2 incrementally; deterministic ids + compaction (the embeddings-store prune bug must
  stay fixed — no unbounded `index.jsonl` growth).
- Honest partial-coverage report; never claim full index when languages were skipped.

### `run "Fix failing test" --workflow auto`
- Workflow selector (PR-000.1 + PR-003): localized bugfix → OC Flow; formal/high-risk → SDD.
- OC Flow: surgical context (envelope required), local-first inspection BEFORE any LLM spend,
  bounded diagnosis (reproduce → 3 hypotheses → fix → verify → escalate), checkpoint before
  mutation, rollback on failure.
- Output: workflow + why, patch, inspection result, cost/confidence, artifacts, next action.

## Hardening guardrails (book §9 invariants)

- No fake success (verify must fail honestly when zero tests ran).
- No uncontrolled loops (attempt budgets enforced).
- Low token use (budgets enforced; KG-first; compression on repeated failure).
- Actionable errors (typed RuntimeErrorCode + what-to-do-next).
- Secure by default (forbidden paths blocked; secrets redacted before any provider call).
- Resumable (interrupt → `session resume` restores state).

## First-run failure modes to test explicitly

No provider configured (must still do local-first work); no tests in repo (OC Flow degrades, says
so); dirty worktree (warn); air-gapped (no external calls); huge repo (index stays bounded);
ambiguous task (intent-clarify, ask once, then proceed).

## Acceptance

The first-run benchmark (doc 57) automates this sequence on a fixture repo and must pass in CI
before 1.0.
