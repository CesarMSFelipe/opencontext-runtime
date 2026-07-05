# Claude Code

## Purpose
Use stable, redacted context packs with Claude Code-style terminal workflows.
Keep `CLAUDE.md` concise and let OpenContext produce task-specific packs.

## Setup

```bash
opencontext setup claude-code
```

This creates:
- `~/.claude/mcp.json` — MCP server config
- `~/.claude/CLAUDE.md` — Instructions with all CLI commands
- `~/.claude/settings.json` — Pre-approved MCP tools
- project-local `.claude/commands/` and `.claude/agents/` — slash commands + SDD agent profiles

Use `--scope global` to write the `~/.claude` files to your home dir; default scope is local.
`opencontext agent init --target claude-code` only writes a project-root `CLAUDE.md` — it does not wire MCP/settings.

## Available Commands (via bash)

```bash
# Code exploration
opencontext pack . --query "Review authentication" --mode plan --copy
opencontext index .
opencontext inspect repomap

# Health & maintenance
opencontext verify
opencontext update
opencontext upgrade

# Plugin management
opencontext plugin search
opencontext plugin install <name>
opencontext plugin update

# Configuration
opencontext config show
opencontext config reconfigure plugins
opencontext config backup
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `opencontext_search` | Find symbols by name |
| `opencontext_context` | Build task-specific code context |
| `opencontext_callers` / `opencontext_callees` | Trace call flow |
| `opencontext_impact` | Check change scope |
| `opencontext_node` | Get symbol details |
| `opencontext_files` | Browse indexed files |
| `opencontext_status` | Check KG health |
| `opencontext_trace` | Find the shortest path between two symbols in the call graph |
| `opencontext_replace_symbol_body` | Replace a named symbol's definition span with new source |
| `opencontext_insert_before_symbol` | Insert source immediately before a named symbol |
| `opencontext_insert_after_symbol` | Insert source immediately after a named symbol |
| `opencontext_rename_symbol` | Rename a symbol at its definition and call-graph references |
| `opencontext_run` | Drive the SDD agentic loop in-process using the host's selected model |

## Related Commands

```bash
opencontext agent init --target claude-code
opencontext agent-context "Review access control" --target claude-code --copy
opencontext doctor security
```
