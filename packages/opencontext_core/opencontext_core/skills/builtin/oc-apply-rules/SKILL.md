---
name: oc-apply-rules
trigger: apply, implement, code
version: 0.1.0
---

# oc-apply-rules

Actionable rules for the SDD apply phase. Kept compact for executor context.

## Rules

- Climb the ladder before adding code: does it need to exist at all? Reach for the stdlib or a native feature before a dependency, an existing symbol before a new one, one line before fifty.
- Make surgical edits scoped to the current task; no gold-plating, no speculative flexibility.
- Match the surrounding patterns, naming, and idioms; reuse over reinvention.
- Delete dead code you touch; add no abstraction (interface, factory, base class) without a second caller today.
- Keep each edit minimal and reversible; every change must pass its gates before you move on.
