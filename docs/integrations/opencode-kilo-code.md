# OpenCode & Kilo Code

## Purpose
OpenCode and Kilo Code share a compatible config format. OpenContext
generates MCP config, SDD orchestrator profile, and AGENTS.md instructions.

## Setup

```bash
opencontext onboard
opencontext agent init --target opencode
opencontext agent init --target kilo-code
```

For OpenCode this creates:
- `~/.config/opencode/mcp.json` — MCP server config
- `~/.config/opencode/agents/gentle-orchestrator.json` — SDD orchestrator profile
- `~/.config/opencode/AGENTS.md` — Instructions

For Kilo Code:
- `~/.config/kilo/mcp.json` — MCP server config
- `~/.config/kilo/AGENTS.md` — Instructions

## Available Commands

```bash
# Code exploration
opencontext pack . --query "Review auth" --mode plan --copy
opencontext index .
opencontext inspect repomap

# SDD workflow
opencontext init        # Initialize SDD context
# Then in the agent: /sdd-new <change>

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

The installed `gentle-orchestrator` agent profile gives OpenCode access to
the full SDD lifecycle via the knowledge graph MCP tools.

## MCP Tools (all 8)

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
opencontext agent init --target opencode
opencontext agent init --target kilo-code
opencontext agent-context "Explain auth flow" --target opencode --copy
```
