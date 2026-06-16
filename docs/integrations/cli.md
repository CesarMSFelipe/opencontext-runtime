# OpenContext CLI

## Purpose

The CLI is the primary user adapter. It stays thin and calls core services.

## Current Status

The CLI provides a full interactive TUI menu (10 options), setup wizards, knowledge graph tools,
context pack generation, SDD workflow harness, plugin management, agent integration, and system health checks.

## Interactive Menu

Running `opencontext` with no subcommand launches an interactive menu:

| # | Option | Action |
|---|--------|--------|
| 1 | Start Installation | Run `opencontext install` with re-run detection |
| 2 | Upgrade Tools | Upgrade all OpenContext packages (table output) |
| 3 | Sync Configs | Sync agent configurations |
| 4 | Upgrade + Sync | Combined flow |
| 5 | Configure Models | Run configuration wizard with model prompts |
| 6 | Create your own Agent | Run `opencontext agent init` |
| 7 | OpenCode Community Plugins | Browse and install plugins |
| 8 | OpenCode SDD Profiles | Configure SDD profiles interactively |
| 9 | Manage Backups | Sub-menu: create, list, restore, clean backups |
| 10 | Managed Uninstall | Run `opencontext clean` |

## Commands

```bash
# Menu
opencontext                          # Launch interactive TUI menu

# Setup & Indexing
opencontext install                  # Auto-detect & configure (with re-run detection)
opencontext install --yes            # Non-interactive (CI-friendly)
opencontext config                   # Run configuration wizard (auto-detected)
opencontext config wizard            # Interactive TUI wizard
opencontext config show              # View preferences
opencontext index .                  # Index project for knowledge graph
opencontext doctor                   # Health check
opencontext doctor deep              # Deep runtime diagnostics

# Context Packs
opencontext pack . --query "Review auth" --mode plan --copy
opencontext pack . --query "Review auth" --mode review --format json
opencontext pack diff --base main --head HEAD

# Knowledge Graph
opencontext knowledge-graph search "authenticate" --limit 20
opencontext knowledge-graph callers "authenticate_user"
opencontext knowledge-graph callees "authenticate_user"
opencontext knowledge-graph impact "authenticate_user" --radius 2
opencontext knowledge-graph status

# SDD Workflow
opencontext harness run --workflow sdd --task "Implement OAuth2"
opencontext harness list

# Plugins
opencontext plugin search
opencontext plugin install security-audit
opencontext plugin list

# Agent Integration
opencontext agent init --target opencode
opencontext agent init --target claude-code
opencontext agent-context "Review auth" --target cursor --copy

# Updates
opencontext update                   # Check for updates
opencontext upgrade                  # Upgrade all packages (per-package status)
```

## Related Commands

```bash
opencontext agent-context "Review access control" --target codex --copy
opencontext pack . --query "review auth" --copy
```

## Implemented Code

- `packages/opencontext_cli/opencontext_cli/main.py` — Entry point, dispatch, version, config discovery
- `packages/opencontext_cli/opencontext_cli/commands/menu_cmd.py` — TUI menu (10 options + backup sub-menu)
- `packages/opencontext_cli/opencontext_cli/commands/config_cmd.py` — Config wizard, show, get, set
- `packages/opencontext_cli/opencontext_cli/commands/update_cmd.py` — Update check and unified upgrade
- `packages/opencontext_api/opencontext_api/main.py` — API adapter
- `packages/opencontext_core/opencontext_core/runtime.py` — Core runtime
