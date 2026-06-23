---
name: oc-review-rules
trigger: review, code review
version: 0.1.0
---

# oc-review-rules

Actionable rules for the SDD review phase. Kept compact for executor context.

## Rules

- One finding per line: path:line: severity: problem. fix.
- Lead with correctness and security, then performance, then maintainability, then economy.
- Flag over-engineering: reinvented stdlib, single-implementation abstractions, dead or unused code, a dependency a few lines would replace.
- Ground every claim with opencontext_impact / callers before asserting; a guess is not a finding.
- Code added but not needed is a finding, even when correct.
