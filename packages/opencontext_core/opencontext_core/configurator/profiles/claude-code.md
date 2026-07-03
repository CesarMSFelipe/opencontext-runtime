# OpenContext — Claude Code Profile

OpenContext gives you a semantic knowledge graph + verified context for this project.

## MCP Tools (pre-approved)

**Read tools** — always safe to call:
- `opencontext_context` — get verified, minimal context for a task
- `opencontext_search` — find symbols by name
- `opencontext_callers` — who calls this function?
- `opencontext_callees` — what does this function call?
- `opencontext_impact` — blast radius before editing
- `opencontext_node` — get one symbol's details
- `opencontext_files` — indexed file structure
- `opencontext_status` — index health
- `opencontext_trace` — trace a call chain

**Edit tools** — target exact symbol boundaries:
- `opencontext_replace_symbol_body` — replace a function/class body
- `opencontext_insert_before_symbol` — insert code before a symbol
- `opencontext_insert_after_symbol` — insert code after a symbol
- `opencontext_rename_symbol` — rename across the codebase

## Recommended workflow

1. Before any edit: call `opencontext_impact` on the symbol you're about to change
2. For context: call `opencontext_context` with your task description
3. For edits: use `opencontext_replace_symbol_body` instead of writing raw file edits

## Running workflows (`opencontext_run`)

Claude Code does not support MCP sampling, so OpenContext cannot execute with
your model. With no provider configured, a mutation run returns
`status: "agent_execute"` — a working handoff, not a dead end:

1. Read the returned `task_contract` and `context.items`.
2. Make the edits yourself with your own tools.
3. Call `opencontext_session_apply` with `kind="agent_edits"` and
   `payload.changed_files` (add `payload.test_command` when a test proves the
   change), exactly as given in the response's `follow_up`. OpenContext then
   verifies the edits, records receipts, and completes the run.
4. If it reports `inspection_failed` or `needs_verification`, fix and re-call.

## Keep the index fresh

Run `opencontext index .` after large changes.
