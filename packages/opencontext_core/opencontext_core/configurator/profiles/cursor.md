# OpenContext — Cursor Profile

OpenContext gives you a semantic knowledge graph + verified context for this project.

## MCP Tools (available in Cursor's agent panel)

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

1. In Cursor's agent panel, use `@opencontext_context 'explain the auth flow'`
2. Before any edit: call `@opencontext_impact` on the symbol you're about to change
3. For context: call `@opencontext_context` with your task description

## Keep the index fresh

Run `opencontext index .` after large changes.
