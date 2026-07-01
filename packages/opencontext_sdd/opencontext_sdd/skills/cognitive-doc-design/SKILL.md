---
name: cognitive-doc-design
description: "Trigger: writing guides, READMEs, RFCs, onboarding, architecture, or review-facing docs. Design docs that reduce cognitive load."
license: Apache-2.0
metadata:
  author: opencontext-runtime
  version: "1.0"
---

## Activation Contract

Load this skill when producing any document a human will read: guides, READMEs, RFCs, architecture docs, onboarding, or review-facing documentation.

## Hard Rules

- Start with the minimum useful document. Do not expand scope beyond what the reader needs.
- Use short sections with clear headings. One concept per section.
- Put reference material (API tables, config keys, command flags) at the end, not inline.
- Preclude prose explanations of what code already expresses clearly.
- Write for the reader who has context about the project but needs to understand this specific topic.

## Decision Gates

| Situation | Approach |
|---|---|
| Explaining a concept | Start with a one-paragraph summary, then expand |
| Documenting an API | One table per endpoint, examples after |
| Writing a guide | One section per step, prerequisites first |
| Architecture doc | Context → Decision → Consequence per ADR |

## Execution Steps

1. Identify the reader's context level and the minimum question they need answered.
2. Outline: title → one-paragraph summary → expandable sections.
3. Write each section as the minimum needed for that subtopic.
4. Move reference tables, config keys, and command flags to the end.
5. Remove every sentence that does not carry information the reader needs.
