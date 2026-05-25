# Five-Minute Setup

OpenContext should be useful in less than five minutes on a normal local
project. The default path requires no API key, no external provider, no network
tools, no MCP, and no file-writing agent behavior.

## 1. Install

```bash
pipx install opencontext-runtime
```

For local repository development:

```bash
pip install -e packages/opencontext_core -e packages/opencontext_profiles -e packages/opencontext_cli -e packages/opencontext_api
```

## 2. Configure (Optional but Recommended)

Run the interactive wizard to customize your preferences:

```bash
opencontext config wizard
```

This guides you through security mode, features, token budgets, agent integrations,
and plugin settings. You can skip this step and use defaults — all features work
out of the box with safe defaults.

Quick reference:
```bash
opencontext config show              # View current preferences
opencontext config reconfigure tokens   # Change just token budgets
opencontext config reconfigure plugins  # Browse & install plugins interactively
opencontext plugin list              # See installed plugins
opencontext plugin search            # Find available plugins
opencontext verify                   # Check everything works
```

## 3. Initialize

```bash
cd my-project
opencontext install
```

`opencontext install` works on **Linux, macOS, and Windows** (via PowerShell). It auto-detects
your project stack and configures SDD/TDD, project index, knowledge graph, and agent integrations
in one step. Use `opencontext install --yes` for non-interactive setup.

If you prefer more control, use the individual commands:

```bash
opencontext init --template python    # Choose a stack template
opencontext onboard .                 # Full guided onboarding
```

## 4. Check Safety

```bash
opencontext doctor
opencontext doctor security
opencontext doctor tools
```

Expected defaults:

- external providers disabled,
- native tools disabled,
- MCP disabled,
- network denied,
- file writes denied,
- traces sanitized.

## 5. Generate Useful Context

```bash
opencontext pack . --query "Explain this project" --mode plan --copy
opencontext agent-context "Review access control" --target codex --copy
```

If clipboard support is unavailable, OpenContext prints the pack instead.

## 6. Optional: Agent Integration

Configure MCP for AI agents:

```bash
opencontext onboard . --setup-mcp
```

This writes MCP configuration to `~/.config/opencode/mcp.json` for OpenCode integration.
Supports 13+ AI coding agents.

## Optional: Ask With Mock Mode

```bash
opencontext ask "Where is authentication implemented?"
```

The default mock provider is deterministic and local. Real provider adapters
must be enabled explicitly by policy.

## Optional: ContextBench CI

```bash
opencontext ci-check init
opencontext ci-check run
```

Initialize and run automated code quality checks locally or in CI.
See [CI Checks](ci-checks.md) for details.

## Mental Model

```text
User Config (global)  ─┐
                       ├──> OpenContext Core
Project Config (local) ─┘
                           -> Technology Profiles
                           -> Workflow Packs
                           -> Adapters / Integrations
```

The core is universal and secure. User config controls global preferences; project
config controls per-project settings. Profiles provide optional stack intelligence.
