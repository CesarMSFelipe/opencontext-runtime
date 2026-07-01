---
name: work-unit-commits
description: "Trigger: implementation, commit splitting, chained PRs, or keeping tests and docs with code. Plan commits as reviewable work units."
license: Apache-2.0
metadata:
  author: opencontext-runtime
  version: "1.0"
---

## When to Use

Use this skill when deciding what belongs in each commit or PR, splitting a feature into reviewable work, or preparing commits before opening a PR.

## Critical Rules

| Rule | Requirement |
|---|---|
| Commit by work unit | A commit represents a deliverable behavior, fix, or docs unit |
| Keep tests with code | Tests belong in the same commit as the behavior they verify |
| Keep docs with the change | Docs belong with the feature or workflow they explain |
| Tell a story | A reviewer should understand why each commit exists from its diff |

## Work Unit Checklist

- [ ] The commit has one clear purpose
- [ ] The repo still makes sense after applying only this commit
- [ ] Tests or docs for this unit are included when relevant
- [ ] Rollback is reasonable without reverting unrelated work
- [ ] The commit message explains the outcome, not the file list

## SDD Relationship

When SDD forecasts high risk: follow `delivery_strategy` — ask on `ask-on-risk`, auto-slice on `auto-chain`, require `size:exception` on over-budget `single-pr`.

## Commands

```bash
git diff --stat
git log --oneline -5
```
