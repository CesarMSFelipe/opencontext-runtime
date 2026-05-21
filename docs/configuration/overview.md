# Overview

Configuration is safe by default and deep-merged onto built-in defaults. There are two
configuration layers:

| Layer | File | Scope |
|-------|------|-------|
| **User Preferences** | `~/.config/opencontext/user-config.json` | Global (all projects) |
| **Project Config** | `./opencontext.yaml` | Per-project |

## User Preferences (Interactive)

Run the configuration wizard to customize your global preferences:

```bash
opencontext config wizard
```

This guides you through security mode, features, token budgets, agent integrations,
and plugin settings. See [User Configuration](user-config.md) for details.

Quick commands:

```bash
opencontext config show              # View current config
opencontext config set token_budget 15000   # Set a value
opencontext config get token_budget         # Get a value
opencontext config reconfigure security     # Reconfigure one section
```

## Plugin Management

```bash
opencontext plugin list              # List installed plugins
opencontext plugin install security-audit    # Install a plugin
opencontext plugin enable <name>      # Enable a plugin
```

See [Plugin System](plugins.md) for full documentation.

## Project Config

Most users should run `opencontext onboard` and avoid manual YAML until they need provider,
memory, output, or workflow customization.

Config models are implemented in `packages/opencontext_core/opencontext_core/config.py` and loaded
through `load_config()`, which deep-merges project YAML onto safe defaults. Security, provider,
tool, memory, cache, output, retrieval, context packing, embeddings, workflow, server, egress,
latency, and context-layer policies are represented explicitly.

Some fields are active runtime controls today; others are policy scaffolds for future adapters. The
defaults are still the important contract: external providers, native tools, MCP execution, network
egress, raw traces, semantic cache, and automatic memory harvesting are off unless policy enables
them.

## Related Commands
```bash
opencontext config wizard
opencontext config show
opencontext plugin list
opencontext init --template generic
opencontext init --template enterprise
opencontext doctor security
opencontext provider simulate --provider openai --classification confidential
```

## More
- [User Configuration](user-config.md) — Interactive wizard and preferences
- [Plugin System](plugins.md) — Install, develop, and manage plugins
- [Configuration Reference](reference.md) — Full YAML schema
- [Templates](templates.md) — Starter templates
