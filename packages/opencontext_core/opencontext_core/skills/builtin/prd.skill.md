# Skill: prd

Convert a vague idea into a structured brief before SDD starts.

## Trigger
- User describes a feature/change without clear requirements
- Task scope is unclear
- Multiple interpretations are possible

## Output format

Produce a structured brief:

```md
## Objective
What we want to achieve (one sentence).

## Context
Why this change exists now.

## Non-goals
What we explicitly will NOT do.

## Constraints
Architecture, APIs, compatibility, performance, security, style.

## Acceptance criteria
Numbered, verifiable list. Each item must be testable.

## Risks
What could break or be affected.

## Testing strategy
Unit / integration / e2e / regression / manual.
```

## Rules
- Ask clarifying questions BEFORE writing the brief if the intent is ambiguous.
- Non-goals are mandatory — they prevent scope creep in later phases.
- Acceptance criteria must map 1:1 to test scenarios in oc-spec.
- Do NOT start implementation. This is input to SDD, not a task.
