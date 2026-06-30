# OpenCode & Kilo Code

## Purpose
OpenContext generates MCP config, persona files, and AGENTS.md instructions for
OpenCode and Kilo Code.

## Setup

```bash
opencontext onboard
opencontext setup opencode      # or: opencontext setup opencode --scope global
opencontext setup kilo-code
```

For OpenCode (`--scope global`) this creates:
- `~/.config/opencode/mcp.json` — MCP server config
- `~/.config/opencode/agents/oc-*.md` — OpenContext persona profiles
- `AGENTS.md` (project root) — Instructions

For Kilo Code (`--scope global`):
- `~/.config/kilo/mcp.json` — MCP server config
- `AGENTS.md` (project root) — Instructions

With the default `--scope local`, project instructions are written to `AGENTS.md`. OpenCode MCP/persona config may still be home-scoped when the host requires it; JSON setup output must report those global writes explicitly.

## Available Commands

```bash
# Code exploration
opencontext pack . --query "Review auth" --mode plan --copy
opencontext index .
opencontext inspect repomap

# SDD workflow
opencontext install     # Initialize project config and SDD context
# Then in the agent: /oc-new <change>

# Health & updates
opencontext verify
opencontext update
opencontext upgrade

# Plugin management
opencontext plugin search
opencontext plugin install <name>
opencontext plugin update
opencontext plugin info <name>
opencontext plugin list --json

# Configuration
opencontext config show
opencontext config reconfigure plugins
opencontext config backup
opencontext config restore <id>
```

## SDD Orchestrator Profile

The installed OpenCode agent profile gives access to the SDD lifecycle through the configured OpenContext MCP tools.

## MCP Tools

| Tool | Purpose |
|------|---------|
| `opencontext_search` | Find symbols by name across the codebase |
| `opencontext_context` | Build relevant code context for a task |
| `opencontext_callers` / `opencontext_callees` | Trace call flow |
| `opencontext_impact` | Analyze what code is affected by changing a symbol |
| `opencontext_node` | Get details about a specific symbol |
| `opencontext_files` | Get indexed file structure |
| `opencontext_status` | Check index health and statistics |
| `opencontext_trace` | Find the shortest path between two symbols in the call graph |
| `opencontext_replace_symbol_body` | Replace a named symbol's definition span with new source |
| `opencontext_insert_before_symbol` | Insert source immediately before a named symbol |
| `opencontext_insert_after_symbol` | Insert source immediately after a named symbol |
| `opencontext_rename_symbol` | Rename a symbol at its definition and call-graph references |
| `opencontext_run` | Drive the SDD agentic loop in-process using the host's selected model |

## Related Commands

```bash
opencontext setup opencode
opencontext setup kilo-code
opencontext agent-context "Explain auth flow" --target opencode --copy
```
