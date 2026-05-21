# Cursor

## Purpose
Cursor uses `.cursor/rules/*.mdc` for project rules. OpenContext generates
a rule file with MCP tool docs and all CLI commands.

## Setup

```bash
opencontext onboard
opencontext agent init --target cursor
```

This creates `~/.cursor/rules/opencontext.mdc`.

## Available Commands (via Terminal)

```bash
# Code exploration
opencontext pack . --query "Review auth" --mode plan --copy
opencontext index .
opencontext inspect repomap

# Health & updates
opencontext verify
opencontext update
opencontext upgrade

# Plugins
opencontext plugin search
opencontext plugin install <name>
opencontext plugin list

# Config
opencontext config show
opencontext config reconfigure plugins
```

## MCP Tools

Cursor supports MCP via its config. Run `opencontext onboard . --setup-mcp`
to configure, then use the 8 KG tools directly.

## Related Commands

```bash
opencontext agent init --target cursor
opencontext agent-context "Review access control" --target cursor --copy
```
