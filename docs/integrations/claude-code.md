# Claude Code

## Purpose
Use stable, redacted context packs with Claude Code-style terminal workflows.
Keep `CLAUDE.md` concise and let OpenContext produce task-specific packs.

## Setup

```bash
opencontext onboard
opencontext agent init --target claude-code
```

This creates:
- `~/.claude/mcp.json` — MCP server for 8 KG tools
- `~/.claude/CLAUDE.md` — Instructions with all CLI commands
- `~/.claude/settings.json` — Pre-approved MCP tools

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

## MCP Tools (direct)

| Tool | Purpose |
|------|---------|
| `opencontext_search` | Find symbols by name |
| `opencontext_context` | Build task-specific code context |
| `opencontext_callers` / `opencontext_callees` | Trace call flow |
| `opencontext_impact` | Check change scope |
| `opencontext_node` | Get symbol details |
| `opencontext_files` | Browse indexed files |
| `opencontext_status` | Check KG health |

## Related Commands

```bash
opencontext agent init --target claude-code
opencontext agent-context "Review access control" --target claude-code --copy
opencontext doctor security
```
