---
name: comment-writer
description: "Trigger: PR feedback, issue replies, reviews, Slack messages, or GitHub comments. Write warm, direct collaboration comments."
license: Apache-2.0
metadata:
  author: opencontext-runtime
  version: "1.0"
---

## When to Use

Load this skill whenever you write a comment that another human will read: GitHub PR/issue comments, review feedback, maintainer replies, or async project updates.

## Voice Rules

| Rule | Requirement |
|---|---|
| Be useful fast | Start with the actionable point. Do not recap the whole PR before feedback |
| Be warm and direct | Sound like a thoughtful teammate, not a corporate bot |
| Keep it short | Prefer 1 to 3 short paragraphs or a tight bullet list |
| Explain why | Give the technical reason when asking for a change |
| Avoid pile-ons | Comment on the highest-value issue, not every tiny preference |
| No em dashes | Use commas, periods, or parentheses instead |

## Comment Formula

```
<Direct observation or request>

<Why it matters, only if needed>

<Concrete next action>
```

## Examples

**Good**: "I think we should name this variable `user_id` instead of `uid` to match the project naming convention in the style guide."

**Skip**: "Looks good to me" (use an approval, not a comment).

## Language Domain

Write in the target context language by default. For Spanish comments, use neutral/professional Spanish unless the context explicitly calls for regional tone.
