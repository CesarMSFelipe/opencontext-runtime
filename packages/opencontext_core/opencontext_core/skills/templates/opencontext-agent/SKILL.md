---
name: opencontext-agent
description: Automatically invoke OpenContext tools during agent lifecycle events.
triggers:
  - agent session
  - code analysis
  - before edit
  - after tool execution
---

# OpenContext Agent Skill

This skill trains the agent to automatically invoke OpenContext tools at
key lifecycle points without waiting for the user to ask.

## When to use OpenContext tools

| Lifecycle point | Tool | Purpose |
|---|---|---|
| Session start | `opencontext pack . --query "<task>"` | Warm up context before work |
| Before reading | `opencontext context` on the relevant symbol | Focus reading |
| Before editing | `opencontext impact` on the target file | Understand blast radius |
| After tool use | `opencontext verify` | Quick health check |
| Before stop | `opencontext pack . --query "<summary>"` | Persist context for next session |

## Rules

1. **Automatic — do not ask**. If the orchestrator fires a hook event and
   the tool is available, run it. The user opted in during install.
2. **Context window aware**. Keep `--max-tokens` at 2000–3000 for pack
   commands. Use `--mode plan` for exploration, `--mode implement` for
   implementation.
3. **Non-blocking**. If a tool call fails (timeout, not installed, network
   error), log a warning and continue. Never block the user.
4. **No duplication**. If `opencontext pack` was already called with the
   same query, skip it. Avoid redundant calls.
5. **Respect quiet hours**. Do not call network-backed tools if the user
   is working offline (detected via connectivity check).
