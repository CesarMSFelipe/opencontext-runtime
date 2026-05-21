# Configuration & User Preferences

OpenContext uses a two-layer configuration system:

1. **Project Config** (`opencontext.yaml`) — Per-project settings (security mode, features, providers)
2. **User Preferences** (`~/.config/opencontext/user-config.json`) — Global user choices (token budgets, agent integrations, enabled plugins)

---

## Interactive Wizard

The configuration wizard guides you through all available options step by step:

```bash
opencontext config wizard
```

### Steps

| Step | Area | What You Choose |
|------|------|----------------|
| 1 | **Security** | `private_project` (local), `enterprise` (team), `air-gapped` (offline) |
| 2 | **Features** | Knowledge Graph, Call Graph, Learning System, Governance, Embeddings, MCP, Git |
| 3 | **Tokens** | Default budget per operation, max input tokens |
| 4 | **Agents** | OpenCode, Claude Code, Cursor, Windsurf, Kilo Code |
| 5 | **Plugins** | **Interactive browser**: see available plugins, choose which to install |
| 6 | **Learning** | Auto-optimize budgets, anonymous sharing |

Step 5 now shows a live table of plugins from the registry with their versions and descriptions.
You can install any of them with y/n prompts — no need to remember separate commands.

At the end you get a summary and confirm before saving.

### Non-Interactive Mode

For CI/CD and automated setups:

```bash
opencontext config wizard --non-interactive
```

This uses sensible defaults without any prompts.

---

## Quick Commands

```bash
# View current configuration
opencontext config show

# Reset to factory defaults
opencontext config reset

# Reconfigure a specific area
opencontext config reconfigure security
opencontext config reconfigure features
opencontext config reconfigure tokens
opencontext config reconfigure agents
opencontext config reconfigure plugins      # Interactive plugin browser

# Set or get individual values
opencontext config set token_budget 15000
opencontext config get token_budget
```

---

## Backup & Restore

Configurations are automatically backed up before every change.
You can also manage backups manually:

```bash
# Create a manual backup
opencontext config backup

# List saved backups
opencontext config backups

# Restore from a specific backup
opencontext config restore <backup-id>

# Clean up old backups (keeps last 30 days by default)
opencontext config cleanup --keep-days 30
```

Backups are stored at:
```
~/.config/opencontext/backups/
```

### How Auto-Backup Works

Every time you change a configuration (`config set`, `config wizard`, `config reconfigure`),
OpenContext automatically creates a backup of the **current state before the change**.
This means you can always roll back to the previous configuration.

---

## Health Verification

Check that OpenContext is working correctly:

```bash
# Run all health checks
opencontext verify

# Machine-readable output for CI
opencontext verify --json
```

The verification checks:
- **Python Version** — 3.12+ required
- **User Config** — Valid configuration file
- **Knowledge Graph** — Database exists and is queryable
- **MCP Server** — Agent integration configuration
- **Plugins** — Installed and enabled/disabled
- **Installation State** — Tracked components
- **Disk Space** — Sufficient free space

---

## Self-Update

Check for and apply OpenContext updates:

```bash
# Check for updates (cached 24 hours)
opencontext update

# Force fresh check from PyPI
opencontext update --force

# Check and install the latest version
opencontext upgrade
```

The update check uses the PyPI JSON API and caches results for 24 hours.
Results are also stored in `~/.config/opencontext/state.json`.

---

## Installation State

OpenContext tracks what components are installed, their versions, and
operation timestamps in a state file:

```
~/.config/opencontext/state.json
```

This file is managed automatically by the system. It tracks:
- Components and their versions
- Installed plugins (name, version, source)
- Last sync, verification, and update check timestamps
