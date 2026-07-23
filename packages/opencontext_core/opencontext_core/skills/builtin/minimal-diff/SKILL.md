---
name: minimal-diff
trigger: apply, implement, code, mutate
version: 0.1.0
---

# minimal-diff

The smallest-change code-generation signal. Kept compact for executor context.

## Rules

- Produce the SMALLEST change that makes the task pass; nothing more.
- Climb the ladder before adding code: does it need to exist at all (YAGNI)? reach for the stdlib or an existing symbol before writing new code; one line before fifty.
- No speculative abstractions: no interface, factory, or base class without a second caller today; no boilerplate "for later".
- Delete dead code you touch. Boring over clever.
