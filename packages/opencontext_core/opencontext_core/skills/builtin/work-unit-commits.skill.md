# Skill: work-unit-commits

One commit per logical work unit. No giant commits. No "WIP" commits.

## What is a work unit
- A single task from oc-tasks
- A test + its implementation
- A refactor step
- A documentation update

## Commit format

```
<type>(<scope>): <what changed>

<optional body: why, not what>
```

Types: feat, fix, refactor, test, docs, chore

## Rules
- Commit after each work unit, not at the end of the day.
- Each commit must leave the suite GREEN. Never commit broken code.
- If you are touching 3+ unrelated things, split into separate commits.
- Commit message describes the WHY, not just the WHAT.
- Do NOT use "WIP", "fix stuff", "changes", "updates" as messages.

## Anti-patterns to avoid
- One commit for an entire feature
- Mixing test + implementation + refactor in one commit
- Committing commented-out code
- "fix previous commit" commits (amend or squash instead)
