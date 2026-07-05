# OpenContext — Codex Profile

OpenContext gives you a semantic knowledge graph + verified context for this project.

## How Codex uses OpenContext

Setup registers the OpenContext MCP server in `~/.codex/config.toml`
(`[mcp_servers.opencontext]`), so Codex calls the MCP tools directly:
`opencontext_context`, `opencontext_search`, `opencontext_impact`,
`opencontext_node`, `opencontext_status`, and the session tools.

## Recommended workflow

1. For context: call `opencontext_context` with your task description
2. Before any edit: call `opencontext_impact` on the symbol you're about to change
3. Without MCP, fall back to the CLI: `opencontext pack . --query 'your task' --copy`

## Running workflows (`opencontext_run`)

Codex does not support MCP sampling, so OpenContext cannot execute with your
model. With no provider configured, a mutation run returns
`status: "agent_execute"` — a working handoff, not a dead end:

1. Read the returned `task_contract` and `context.items`.
2. Make the edits yourself with your own tools.
3. Call `opencontext_session_apply` with `kind="agent_edits"` and
   `payload.changed_files` (add `payload.test_command` when a test proves the
   change), exactly as given in the response's `follow_up`. OpenContext then
   verifies the edits, records receipts, and completes the run.
4. If it reports `inspection_failed` or `needs_verification`, fix and re-call.

## Keep the index fresh

Run `opencontext index .` after large changes to ensure context is up to date.
