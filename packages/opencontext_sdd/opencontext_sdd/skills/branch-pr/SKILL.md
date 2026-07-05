---
name: branch-pr
description: "Trigger: creating, opening, or preparing PRs for review. Create Gentle AI pull requests with issue-first checks."
license: Apache-2.0
metadata:
  author: opencontext-runtime
  version: "2.0"
---

## When to Use

Use this skill when:
- Creating a pull request for any change
- Preparing a branch for submission
- Helping a contributor open a PR

## Critical Rules

1. **Every PR MUST link an approved issue** — no exceptions
2. **Every PR MUST have exactly one `type:*` label**
3. **Automated checks must pass** before merge is possible

## Workflow

1. Verify issue has `status:approved` label
2. Create branch: `type/description`
3. Implement changes with conventional commits
4. Open PR using the template
5. Add exactly one `type:*` label
6. Wait for automated checks to pass

## Branch Naming

Format: `type/description` — lowercase, no spaces, only `a-z0-9._-` in description.
Types: feat, fix, chore, docs, style, refactor, perf, test, build, ci, revert.

## Conventional Commits

Format: `type(scope): description` or `type: description`
Types: build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test
