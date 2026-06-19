# Getting Started with OpenContext

This guide walks you through the complete OpenContext experience from installation to daily use.

## Prerequisites

- Python 3.12 or later
- pip (Python package manager)
- Git (optional, for git context features)

## Installation

### One-Liner (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh | bash
```

This installs `opencontext-core` and `opencontext-cli` from PyPI (or from source if PyPI packages are not yet available).

### Manual Installation

```bash
pip install opencontext-core opencontext-cli
```

### Development Installation

```bash
git clone https://github.com/CesarMSFelipe/OpenContext-Runtime.git
cd OpenContext-Runtime
pip install -e packages/opencontext_core -e packages/opencontext_cli
```

### Verify Installation

```bash
opencontext --help
```

You should see a list of available commands.

## Quick Start (3 Minutes)

### 1. Install & Configure Your Project

```bash
cd your-project
opencontext install
```

This auto-detects your stack and walks you through:
- `opencontext.yaml` — Project configuration
- Project indexing and knowledge graph
- SDD/TDD harness setup
- Agent integration files
- `.opencontext/` — Working directory for indexes, memory, traces

### 2. Index Your Code

```bash
opencontext index .
```

This scans your codebase and builds a knowledge graph with symbols, files, and relationships.

### 3. Generate Your First Context Pack

```bash
opencontext pack . --query "Explain the authentication flow"
```

This creates a compact, redacted context pack with relevant code snippets and metadata.

### 4. Check Project Health

```bash
opencontext doctor
```

## Daily Workflow

### Search Your Codebase

```bash
# Semantic search
opencontext semantic "user authentication"

# Knowledge graph search
opencontext knowledge-graph search "authenticate"

# Find callers of a function
opencontext knowledge-graph callers "login_user" --depth 2
```

### Understand Impact

```bash
# What would break if I change this?
opencontext knowledge-graph impact "UserService" --radius 3

# Find affected tests
opencontext affected src/auth.py
```

### Build Context for AI Agents

```bash
# For a specific task
opencontext pack . --query "Review the authentication module" --mode review

# For implementation
opencontext pack . --query "Implement OAuth2 login" --mode implement_pack

# Copy to clipboard (if available)
opencontext pack . --query "Explain caching" --copy
```

## Agent Integration

OpenContext integrates with 13+ AI coding agents. Choose your agent:

### Auto-Detect and Install

```bash
opencontext install
```

### Install for Specific Agents

```bash
opencontext install --target claude,cursor,opencode
```

### MCP Server (for Claude Code, Cursor, etc.)

```bash
opencontext mcp
```

This starts an MCP server that exposes knowledge graph tools to your agent.

### Configuration Files

After installation, your agent will have configuration files pointing to OpenContext:

- **Claude Code**: `~/.config/claude/CLAUDE.md`
- **Cursor**: `.cursor/rules/opencontext.mdc`
- **OpenCode**: `AGENTS.md`
- **Windsurf**: `.windsurf/rules/opencontext.md`

## Project Configuration

### Initialize Hints

Create `.opencontexthints` to guide AI agents with project-specific conventions:

```bash
opencontext agent init --target generic
```

Edit the generated `AGENTS.md` to add your conventions:

```
project: My Project

[conventions]
- Use type hints everywhere
- Prefer dataclasses over dicts

[architecture]
- Core logic in domain layer
- Infrastructure in adapters

[warnings]
- Never commit secrets
```

### Set Up CI Checks

Verify your setup is healthy:

```bash
opencontext verify
opencontext doctor
```

### Knowledge Graph

If your project uses git, OpenContext automatically enriches context with history:

```bash
opencontext knowledge-graph search "symbol"
opencontext knowledge-graph impact "ClassName"
```

## Advanced Features

### SDD Workflow

Run Spec-Driven Development workflows via the harness runner:

```bash
# Full SDD lifecycle (6 phases)
opencontext harness run --workflow sdd --task "Implement feature X"

# Explore only
opencontext harness run --workflow explore-only --task "How does auth work?"

# List available workflows
opencontext harness list
```

### Graph Visualization

```bash
opencontext visualize --output repo-graph.svg --format svg
```

### Performance Metrics

```bash
opencontext metrics summary
```

### Interactive TUI

```bash
opencontext tui
```

## Configuration File Reference

Your `opencontext.yaml` controls all behavior:

```yaml
version: "1.0"
project:
  name: "my-project"
  root: "."
security:
  mode: "private_project"
  redaction: true
providers:
  default: "mock/mock-llm"
  enabled: []
tools:
  enabled: false
mcp:
  enabled: false
```

### Security Modes

- `developer`: Local development with tools enabled
- `private_project`: Production-safe defaults
- `enterprise`: Strict compliance mode
- `air_gapped`: No external connections

## Troubleshooting

### "Not a git repository"

OpenContext works without git, but some features (git context, blame) require it:

```bash
git init
```

### "No source files detected"

Make sure your project has code files (.py, .js, .ts, .go, .rs, etc.).

### "Permission denied"

Ensure you have write permissions in the project directory.

### Get Help

```bash
opencontext --help
opencontext install --help
opencontext pack --help
```

## Next Steps

- Read the [Architecture Overview](../architecture/overview.md)
- Explore [Token Efficiency](../token-efficiency/overview.md)
- Learn about [Memory](../memory/overview.md)
- Check [Security Best Practices](../security/threat-model.md)
- Review the [CLI Reference](../integrations/cli.md)

## One-Page Cheat Sheet

```bash
# Setup
opencontext install
opencontext index .

# Search
opencontext semantic "auth flow"
opencontext knowledge-graph search "login"

# Context
opencontext pack . --query "Review auth" --mode review

# Impact
opencontext knowledge-graph impact "UserService"
opencontext affected src/auth.py

# Agents
opencontext agent init --target claude-code
opencontext mcp

# Health
opencontext doctor
opencontext verify
```
