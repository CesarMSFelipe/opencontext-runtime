# Plugin System

OpenContext has an extensible plugin architecture for adding custom functionality.
Plugins can register CLI commands, tools, and hooks.

---

## Quick Start

```bash
# Browse available plugins
opencontext plugin search

# Install from the registry
opencontext plugin install security-audit

# Or during configuration wizard
opencontext config wizard        # Step 5: interactive browser
opencontext config reconfigure plugins  # Same browser anytime
```

---

## Management Commands

### Browse & Search

```bash
# List all available plugins from registry
opencontext plugin search

# Search by name or description
opencontext plugin search audit
opencontext plugin search performance

# Force refresh the registry cache
opencontext plugin search --refresh
```

### Install

```bash
# From the built-in/remote registry
opencontext plugin install security-audit

# Specific version
opencontext plugin install security-audit --ver 0.1.0

# From GitHub (owner/repo)
opencontext plugin install <name> --github owner/repo

# From any URL (tar.gz, zip)
opencontext plugin install <name> --url https://example.com/plugin.zip
```

### Manage

```bash
# List installed plugins
opencontext plugin list
opencontext plugin list --json    # Machine-readable output

# Show plugin details
opencontext plugin info security-audit

# Enable or disable
opencontext plugin enable <name>
opencontext plugin disable <name>

# Remove
opencontext plugin remove <name>

# Update (check for newer versions)
opencontext plugin update              # Check all
opencontext plugin update <name>       # Check specific
```

---

## Interactive Installation

Plugins can be installed from the configuration wizard without remembering commands:

```bash
# During initial setup
opencontext config wizard
# → Step 5 shows available plugins as a table.
#   Choose which ones to install with y/n prompts.

# Any time after setup
opencontext config reconfigure plugins
# → Same interactive browser: see what's available,
#   what's installed, and install new ones.
```

---

## Installation Sources

| Source | Command | Description |
|--------|---------|-------------|
| **Registry** | `opencontext plugin install <name>` | Built-in or remote registry. Default URL: `raw.githubusercontent.com/opencontext/plugin-registry/main/registry.json`. Falls back to built-in if offline. |
| **GitHub** | `--github owner/repo` | Downloads the latest release from GitHub via API. Supports full URL and `.git` suffix. |
| **URL** | `--url <url>` | Direct download from any URL. Supports `.tar.gz` and `.zip` archives. |
| **Config wizard** | `opencontext config reconfigure plugins` | Interactive browser with registry search. |

---

## Registry

The plugin registry provides a catalog of available plugins. It is fetched from:

```
https://raw.githubusercontent.com/opencontext/plugin-registry/main/registry.json
```

- Results are cached for **1 hour**
- Falls back to **built-in plugins** if the remote is unreachable
- Force refresh with: `opencontext plugin search --refresh`

### Built-In Plugins

| Plugin | Description |
|--------|-------------|
| `security-audit` | Security audit and vulnerability scanning |
| `performance` | Performance profiling and optimization suggestions |
| `team` | Team collaboration, shared conventions, peer review |

---

## Safety & Rollback

Plugin installation is safe by design:

- **Auto-backup**: Before installing a plugin, the existing version (if any) is backed up
- **Rollback on failure**: If the installation fails, the backup is automatically restored
- **Checksum verification**: When available, downloads are verified against SHA-256 checksums
- **Idempotent**: Installing the same version again is a no-op (safely skipped)

---

## Installation Location

Plugins are installed to:

```
~/.config/opencontext/plugins/<name>/
```

Each plugin directory contains:

```
plugin.json        # Plugin manifest (name, version, enabled, hooks, source metadata)
plugin.py          # Python entry point
```

Plugin state (versions, install source, timestamps) is also tracked in:

```
~/.config/opencontext/state.json
```

---

## Developing a Plugin

### Structure

```
my-plugin/
├── plugin.json
└── plugin.py
```

### plugin.json

```json
{
  "name": "my-plugin",
  "version": "0.1.0",
  "description": "What my plugin does",
  "author": "Your Name",
  "entry_point": "plugin.py",
  "hooks": [],
  "enabled": true
}
```

Extended fields (auto-populated on install):

```json
{
  "homepage": "https://github.com/example/my-plugin",
  "repository": "https://github.com/example/my-plugin",
  "install_source": "registry",
  "source_url": "https://.../download.tar.gz",
  "installed_at": "2026-05-21T12:00:00",
  "updated_at": "2026-05-21T12:00:00"
}
```

### plugin.py

```python
class OpenContextPlugin:
    @property
    def name(self):
        return "my-plugin"

    @property
    def version(self):
        return "0.1.0"

    def initialize(self, context):
        """Called when the plugin is loaded."""
        pass

    def shutdown(self):
        """Called when the plugin is unloaded."""
        pass

    def register_commands(self, registry):
        """Register CLI commands."""
        pass

    def register_hooks(self, registry):
        """Register event hooks."""
        pass
```

### Installing a Custom Plugin

```bash
# Copy to the plugins directory
cp -r my-plugin ~/.config/opencontext/plugins/

# Verify it appears
opencontext plugin list

# Enable if needed
opencontext plugin enable my-plugin
```

---

## Security Model

Plugins use a deny-by-default permissions model:

```python
class PluginPermissions(BaseModel):
    read_paths: list[str] = []       # Allowlisted read paths
    write_paths: list[str] = []      # Allowlisted write paths
    network_hosts: list[str] = []    # Allowlisted outbound hosts
    mcp_servers: list[str] = []      # Allowlisted MCP servers
```

All capabilities default to denied. Explicitly grant only what the plugin needs.

### Manifest with Permissions

```json
{
  "name": "my-plugin",
  "version": "0.1.0",
  "type": "analyzer",
  "entrypoint": "plugin.py",
  "max_data_classification": "internal",
  "permissions": {
    "read_paths": ["/project/src"],
    "network_hosts": []
  }
}
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Plugin not in list | Wrong directory | Check `~/.config/opencontext/plugins/` |
| Plugin won't enable | Missing entry point | Verify `plugin.py` exists |
| Import errors | Python deps missing | Install required dependencies |
| Plugin not responding | Not loaded | Run `opencontext plugin disable <name>` then `opencontext plugin enable <name>` |
| "Version not available" | Wrong version | Run `opencontext plugin info <name>` to see available versions |
| "Failed to fetch registry" | No network | Falls back to built-in plugins automatically |
