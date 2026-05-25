<p align="center">
  <img src="docs/assets/logo.svg" width="120" alt="OpenContext Logo">
</p>

<h1 align="center">OpenContext Runtime</h1>

<p align="center">
  <b>Context Engineering for AI Agents</b>
</p>

<p align="center">
  <a href="#quick-start"><img src="https://img.shields.io/badge/python-3.12+-00C9A7.svg" alt="Python 3.12+"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/install-curl%20%7C%20bash-00A8E8.svg" alt="Install"></a>
  <a href="#validation"><img src="https://img.shields.io/badge/tests-all%20passing-00C9A7.svg" alt="Tests"></a>
  <a href="#license"><img src="https://img.shields.io/badge/license-MIT-845EC2.svg" alt="MIT License"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#what-it-is">What It Is</a> •
  <a href="#why-opencontext">Why OpenContext</a> •
  <a href="#cli-reference">CLI</a> •
  <a href="#documentation-map">Docs</a> •
  <a href="#agent-integration">Agents</a>
</p>

---

| Method | Platform | Command |
|--------|----------|---------|
| **One-liner** | Linux / macOS | `curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh \| bash` |
| **One-liner** | Windows PowerShell | `irm https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.ps1 \| iex` |
| **pip** | All | `pip install opencontext-cli` |
| **Source** | All | `git clone + pip install -e packages/*` |

Requires **Python 3.12+**. No API keys, no external services, no vector DB required.

---

## Quick Start

Get a project configured and a context pack in your clipboard in under a minute:

```bash
# 1. Install (once)
curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh | bash

# 2. Set up your project (auto-detects stack, SDD/TDD, agents, graph)
cd your-project
opencontext install --yes

# 3. Get task-specific context
opencontext pack . --query "Explain how authentication works" --copy
```

That's it. Three commands. No config files to edit, no API keys to set up.

`opencontext install` works on **Linux, macOS, and Windows**. It auto-detects your project stack, walks you through each step with progress indicators, and sets up the knowledge graph, SDD/TDD harness, agent integrations, and project index — everything needed to start coding with AI assistance.

After installing, fine-tune everything with:
```bash
opencontext config wizard     # Interactive TUI menu
```

---

## Why OpenContext

**The problem:** LLMs are only as useful as the context they receive. Dumping a whole repository into a prompt is:
- **Expensive** — 100K+ tokens per query, even for simple questions
- **Noisy** — most files are irrelevant to the task
- **Dangerous** — secrets, API keys, and untrusted text leak into prompts
- **Hard to audit** — no record of what was sent or why

**The solution:** OpenContext indexes your project, then for each task selects the minimal high-signal subset — redacted, token-budgeted, and traceable. Your AI agent gets what it needs, nothing it shouldn't.

```python
from opencontext_core import OpenContextRuntime

runtime = OpenContextRuntime()
runtime.setup_project(".")
prepared = runtime.prepare_context("Review authentication", max_tokens=6000)

# prepared.context  → compact, redacted, task-specific
# prepared.trace_id → auditable record
```

> "Given a user request, project memory, repository structure, documents, traces, tools, security constraints, and token/cost limits, what is the safest and most useful minimal context/action plan?"

---

## What It Is

OpenContext is a **context engineering runtime** for AI agents. It provides:

- **Code knowledge graph** — SQLite+FTS5 with call graph analysis, impact analysis, and framework route detection (19+ languages)
- **Spec-Driven Development (SDD)** — 6-phase harness (explore → propose → apply → verify → review → archive) with per-phase model assignment and token budgets
- **Agent installer** — 13+ AI coding agents (Claude Code, OpenCode, Cursor, Codex, Windsurf, VS Code Copilot, Kilo Code, and more)
- **Safety layer** — secret redaction, provider policy enforcement, prompt injection boundaries, output exfiltration scanning
- **Local memory** — progressive disclosure with pinned facts, temporal context, search, and garbage collection
- **MCP server** — 8 knowledge graph tools for agent integration
- **Plugin system** — deny-by-default with remote registry and built-in plugins
- **Workflow packs** — repeatable team AI operations with integrity signing
- **Zero-key mode** — everything works locally without API keys or external providers

What it is **not**: a chatbot, UI, vector database, RAG wrapper, or provider SDK. Core is provider-neutral and framework-agnostic.

---

## CLI Reference

### Setup & Indexing

```bash
opencontext install                   # Auto-detect & configure (cross-platform)
opencontext install --yes             # Non-interactive (CI-friendly)
opencontext index .                   # Index project for knowledge graph
opencontext doctor                    # Health check
opencontext doctor deep               # Deep runtime diagnostics
opencontext doctor security           # Security-specific checks
```

### Context Packs

```bash
opencontext pack . --query "Review auth" --mode plan --copy
opencontext pack . --query "Review auth" --mode review --format json
opencontext pack . --query "Review auth" --format toon
opencontext pack diff --base main --head HEAD
```

### Knowledge Graph

```bash
opencontext knowledge-graph search "authenticate" --limit 20
opencontext knowledge-graph callers "authenticate_user"
opencontext knowledge-graph callees "authenticate_user"
opencontext knowledge-graph impact "authenticate_user" --radius 2
opencontext knowledge-graph status
```

### SDD Workflow (Spec-Driven Development)

```bash
opencontext harness run --workflow sdd --task "Implement OAuth2"
opencontext harness run --workflow explore-only --task "How does auth work?"
opencontext harness list
```

### Plugins

```bash
opencontext plugin init my-plugin                   # Scaffold new plugin
opencontext plugin init my-plugin --template advanced  # With lifecycle stubs
opencontext plugin search                           # Browse registry
opencontext plugin install security-audit           # Install from registry
opencontext plugin info security-audit --json       # Details with version check
opencontext plugin list                             # Installed plugins
```

### Configuration

```bash
opencontext config wizard                 # Interactive TUI menu
opencontext config show                   # View preferences
opencontext config set features.knowledge_graph true   # Dot-notation
opencontext config get sdd.tdd_mode                   # Read any path
```

### Agent Integration

```bash
opencontext agent init --target opencode             # Generate AGENTS.md + opencode.json
opencontext agent init --target claude-code           # Generate CLAUDE.md
opencontext agent init --target cursor                # Generate .cursor/rules/
opencontext agent-context "Review auth" --target cursor --copy  # One-off block
```

### Updates

```bash
opencontext update              # Check for updates
opencontext upgrade             # Install latest version
```

OpenContext auto-checks for updates and notifies you after commands when a newer version is available.

---

## Safe By Default

OpenContext ships with a deny-by-default security posture. No external calls, no data leaks, no surprises:

- External providers **disabled** by default
- Tools **disabled** by default
- MCP **disabled** by default
- Network **denied** by default
- Filesystem writes **denied** by default
- Secrets redacted before prompts, traces, cache, memory, and context packs
- Raw traces **disabled** by default
- Missing provider policy **fails closed**

Everything works in **zero-key mode** — you get context packs, repo maps, the knowledge graph, memory, and SDD without any API keys or external dependencies.

---

## Agent Integration

OpenContext is agent-tool neutral. It generates small instruction files that tell your AI agent to request minimal context instead of reading the whole repository.

| Tool | Generated files |
|------|-----------------|
| Generic / Codex | `AGENTS.md` |
| OpenCode | `AGENTS.md` + `opencode.json` |
| Claude Code | `CLAUDE.md` |
| Cursor | `.cursor/rules/opencontext.mdc` |
| Windsurf | `.windsurf/rules/opencontext.md` |
| Kilo Code / OpenClaw | `AGENTS.md` |

```bash
# Recommended workflow
opencontext install
opencontext agent init --target cursor
opencontext pack . --query "my task" --mode plan --copy
```

---

## Documentation Map

| Topic | Guide |
|-------|-------|
| **Getting Started** | [Runtime-first setup](docs/getting-started/runtime-first.md), [CLI install](docs/getting-started/cli-installation.md), [Quickstart](docs/getting-started/quickstart.md), [Troubleshooting](docs/getting-started/troubleshooting.md) |
| **Architecture** | [Overview](docs/architecture/overview.md), [Project intelligence](docs/architecture/project-intelligence-layer.md), [Context pack builder](docs/architecture/context-pack-builder.md), [Safety layer](docs/architecture/safety-layer.md) |
| **Configuration** | [Reference](docs/configuration/reference.md), [Security policy](docs/configuration/security-policy.md), [Provider policy](docs/configuration/provider-policy.md), [User config](docs/configuration/user-config.md) |
| **Workflows** | [SDD workflow](docs/workflows/sdd-workflow.md), [Custom workflows](docs/workflows/custom-workflows.md), [Workflow packs](docs/workflows/workflow-packs.md) |
| **Memory** | [Overview](docs/memory/overview.md), [Context repository](docs/memory/context-repository.md), [Progressive disclosure](docs/memory/progressive-disclosure.md) |
| **Security** | [Threat model](docs/security/threat-model.md), [Data classification](docs/security/data-classification.md), [Prompt security](docs/security/ai-leak-and-prompt-security.md) |
| **Integrations** | [Python SDK](docs/integrations/python-sdk.md), [API](docs/integrations/api.md), [CLI](docs/integrations/cli.md), [GitHub Action](docs/integrations/github-action.md) |
| **Enterprise** | [Air-gapped](docs/enterprise/air-gapped.md), [Governance reports](docs/enterprise/governance-reports.md), [Evidence packs](docs/enterprise/evidence-packs.md) |
| **Development** | [Contributing](docs/development/contributing.md), [Testing](docs/development/testing.md), [Adding a command](docs/development/adding-a-command.md) |
| **Roadmap** | [Current status and planned work](docs/roadmap.md) |

See also the [docs index](docs/README.md) for a complete listing.

---

## Default Configuration

```yaml
security:
  mode: private_project
  fail_closed: true
models:
  default:
    provider: mock
    model: mock-llm
providers:
  external_enabled: false
tools:
  native:
    enabled: false
  mcp:
    enabled: false
traces:
  store_raw_context: false
memory:
  enabled: true
  harvest_after_run: false
  require_approval: true
  store_raw: false
output:
  mode: concise
  max_output_tokens: 1500
```

---

## Validation

```bash
pytest
ruff check .
ruff format --check .
mypy packages/opencontext_core
```

Before publishing, see the [release checklist](docs/release-checklist.md).

---

## License

MIT — see [LICENSE](LICENSE).

## Security

Do not put secrets in GitHub issues, prompts, traces, examples, configs, test fixtures, workflow packs, or memory files. If you find a vulnerability, follow [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [development docs](docs/development/contributing.md).
