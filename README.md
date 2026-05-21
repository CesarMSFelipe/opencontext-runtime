<p align="center">
  <img src="docs/assets/logo.svg" width="120" alt="OpenContext Logo">
</p>

<h1 align="center">OpenContext Runtime</h1>

<p align="center">
  <b>Context Engineering for AI Agents</b>
</p>

<p align="center">
  <a href="#installation"><img src="https://img.shields.io/badge/python-3.12+-00C9A7.svg" alt="Python 3.12+"></a>
  <a href="#installation"><img src="https://img.shields.io/badge/install-curl%20%7C%20bash-00A8E8.svg" alt="Install"></a>
  <a href="#tests"><img src="https://img.shields.io/badge/tests-342%20passed-00C9A7.svg" alt="Tests"></a>
  <a href="#license"><img src="https://img.shields.io/badge/license-MIT-845EC2.svg" alt="MIT License"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#installation">Install</a> •
  <a href="#documentation-map">Docs</a> •
  <a href="#cli-reference">CLI</a> •
  <a href="#agent-integration">Agents</a>
</p>

---

OpenContext is a secure, zero-trust, token-efficient context engineering runtime for LLM applications. It indexes private projects, builds compact repo maps, selects high-signal context, redacts secrets, controls input and output tokens, assembles cache-friendly prompts, records auditable traces, and provides a first-class local memory layer.

It answers one product question:

> Given a user request, project memory, repository structure, documents, traces, tools, security constraints, and token/cost limits, what is the safest and most useful minimal context/action plan?

## What It Is

- A Python 3.12+ context engineering runtime.
- A local-first context packer for AI coding agents.
- A **semantic code knowledge graph** with call graph analysis, impact analysis, and FTS5 search.
- A **Spec-Driven Development (SDD) orchestrator** with 7-phase lifecycle and per-phase model assignment.
- A **skill registry** with auto-discovery, compact rules, and context-aware resolution.
- An **agent installer** supporting 13+ AI coding agents (Claude Code, OpenCode, Cursor, Codex, Windsurf, etc.).
- An **MCP server** exposing 8 knowledge graph tools to AI agents.
- A safety layer for secrets, provider policy, prompt injection boundaries, traces, cache, memory, and exports.
- A workflow scaffold for repeatable team AI operations.
- A technology-agnostic core with optional Technology Profiles.

## What It Is Not

OpenContext is not a chatbot, UI, vector database, simple RAG wrapper, prompt template collection, or provider SDK wrapper. Core does not depend on FastAPI, CLI frameworks, provider SDKs, LangChain, LlamaIndex, Haystack, LiteLLM, DSPy, Docker Compose, Kubernetes, or framework-specific imports.

## Why It Exists

LLMs are only as safe and useful as the context they receive. Dumping a whole repository into a prompt is expensive, noisy, hard to audit, and dangerous when secrets or untrusted text are present. OpenContext makes context selection explicit, measurable, redacted, token-aware, memory-aware, and traceable.

## Start In Two Minutes

### Once Published on PyPI (Simple)

```bash
# Install from PyPI (single package — includes CLI + core + profiles)
pip install opencontext-cli

# Or install specific packages
pip install opencontext-core opencontext-opencontext-profiles opencontext-providers
```

### Runtime-First Quickstart

The default path does not require users to learn OpenContext commands. Install the runtime in
the host application, then call the Python API or HTTP API from your agent harness. This is the
recommended path for IDE extensions, local wrappers, independent developers, and products that want
OpenContext to run quietly behind the scenes.

```bash
pip install opencontext-core opencontext-api
```

```python
from opencontext_core import OpenContextRuntime
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

runtime = OpenContextRuntime()
runtime.setup_project(".")
prepared = runtime.prepare_context("Review authentication", max_tokens=6000)

# Build code knowledge graph
kg = KnowledgeGraph()
kg.index_project(".")
stats = kg.get_stats()
print(f"Indexed: {stats['nodes']} nodes, {stats['edges']} edges")

print("Trace:", prepared.trace_id)
print("Sources:", prepared.included_sources)
print(prepared.context)
```

### Current Development Installation

```bash
git clone https://github.com/CesarMSFelipe/OpenContext-Runtime.git
cd OpenContext-Runtime
pip install -e packages/opencontext_core -e packages/opencontext_cli

cd your-project
opencontext onboard
opencontext pack . --query "Review authentication" --mode plan --copy
```

That is enough to get a compact, redacted, task-specific context pack with source refs, token
accounting, omission reasons, and a trace id. The rest of the documentation explains how to tune
policies, memory, workflows, integrations, and enterprise controls after the basic flow works.

**Publishing to PyPI**: See [docs/guides/pypi-publishing.md](docs/guides/pypi-publishing.md) for the full release checklist and dependency order.

### Does OpenContext Use The Whole Repository?

OpenContext indexes the whole non-ignored repository, but it does not send the whole repository to
the model.

The indexer scans all files allowed by ignore rules, extracts file metadata and symbols, builds a
manifest, and persists that project map locally. For each user task, retrieval and ranking select a
small high-signal subset. Context packing then enforces the token budget, redacts secrets, and
records omission reasons.

Use `.opencontextignore` and `.gitignore` to exclude generated files, vendored dependencies,
virtualenvs, build outputs, logs, caches, private exports, or any source tree that should never be
indexed. The default ignore rules already exclude common directories such as `.git`, `.opencontext`,
`.storage`, `.venv`, `venv`, `node_modules`, `vendor`, `dist`, `build`, cache directories, and logs.

### Runtime-First Flow For An Independent Developer

For a solo developer using Codex, Cursor, Copilot, Claude Code, or a local script, the practical
flow is:

1. Install `opencontext-core` in the project environment.
2. Let a tiny host script, IDE extension, or local agent wrapper call `runtime.setup_project(".")`
   once when the project is opened.
3. For every task, call `runtime.prepare_context("<task>", max_tokens=...)`.
4. Pass `prepared.context` and `prepared.included_sources` to the model instead of dumping the
   whole repository.
5. Keep `prepared.trace_id` with the model response so the run can be audited.

This gives the developer repo-aware assistance without teaching them OpenContext-specific
commands. The CLI is still available when they want terminal control.

## Semantic Search

Search code semantically using vector embeddings:

```bash
# Pure semantic search
opencontext semantic "authentication flow"

# Hybrid search (semantic + keyword)
opencontext semantic "user login" --hybrid --top-k 10
```

## Graph Visualization

Visualize code relationships:

```bash
# Export full graph to DOT
opencontext visualize --output codegraph.dot --max-nodes 100

# Export as SVG (requires graphviz)
opencontext visualize --output codegraph.svg --format svg

# Export call graph for specific symbol
opencontext visualize --symbol authenticate_user --output auth.dot
```

## Performance Metrics

Track token usage, timing, and costs:

```bash
# Show summary
opencontext metrics summary

# Show recent operations
opencontext metrics recent

# Show historical metrics
opencontext metrics history --days 7

# Clear metrics
opencontext metrics clear
```

## Plugin System

OpenContext has a deny-by-default plugin system. Plugins live in `~/.config/opencontext/plugins/`.

```bash
# List installed plugins
opencontext plugin list

# Install a built-in plugin (security-audit, performance, team)
opencontext plugin install security-audit

# Enable/disable
opencontext plugin enable security-audit
opencontext plugin disable security-audit

# Remove a plugin
opencontext plugin remove security-audit

# Search available plugins
opencontext plugin search
```

See [Plugin Documentation](docs/configuration/plugins.md) for development and security model.

## Configuration Wizard

Customize your global preferences interactively:

```bash
# Run the full wizard (6 steps)
opencontext config wizard

# View current configuration
opencontext config show

# Reconfigure specific areas
opencontext config reconfigure security
opencontext config reconfigure tokens

# Set individual values
opencontext config set token_budget 15000

# Reset to factory defaults
opencontext config reset
```

See [User Configuration](docs/configuration/user-config.md) for details.

## Using OpenContext With Different Agents

OpenContext is agent-tool neutral. Codex, Claude Code, OpenCode, Cursor, Windsurf, and similar
tools should all receive the same kind of artifact: compact, redacted, task-specific context with
source references and a trace id. The differences are mostly where each tool expects instructions
or project rules to live.

### Recommended Integration Matrix

| Tool or surface | Best setup | Generated files | How to use it |
| --- | --- | --- | --- |
| Codex | Runtime/API first, CLI optional | `AGENTS.md` | Keep OpenContext instructions in `AGENTS.md`; feed `PreparedContext.context` into the session or ask Codex to use the CLI only when installed. |
| Claude Code | Runtime/API first, CLI optional | `CLAUDE.md` | Put concise OpenContext rules in `CLAUDE.md`; provide context packs as task evidence rather than asking Claude to read the whole repo. |
| OpenCode | Runtime/API first, CLI optional | `AGENTS.md`, `opencode.json` | `opencode.json` points OpenCode at project instructions; OpenContext still prepares context through runtime/API or CLI. |
| Cursor | Runtime/API first, CLI optional | `.cursor/rules/opencontext.mdc` | Use an always-applied rule that tells Cursor to prefer compact OpenContext context over broad file reads. |
| Windsurf | Runtime/API first, CLI optional | `.windsurf/rules/opencontext.md` | Store workspace-scoped rules; pass prepared context into the task when possible. |
| Kilo Code / OpenClaw | Runtime/API first, CLI optional | `AGENTS.md` | Use the generic agent instruction file and provide packed context as evidence. |
| Any custom agent | Runtime/API first | Host-defined | Call `setup_project()` once and `prepare_context()` per task; pass `context`, `included_sources`, and `trace_id` to the model. |

Generate tool-specific instruction files when using the CLI:

```bash
opencontext agent init --target codex
opencontext agent init --target claude-code
opencontext agent init --target opencode
opencontext agent init --target cursor
opencontext agent init --target windsurf
opencontext agent init --target kilo-code
opencontext agent init --target openclaw
```

For runtime-only integrations, generate or ship equivalent instructions in the host application.
The important rule is the same everywhere: ask OpenContext for minimal context before prompting the
model, and treat retrieved context as untrusted evidence.

## LLM Provider Management

OpenContext supports multiple LLM providers through a unified adapter interface:

```bash
# List available providers
opencontext llm list

# Chat with a provider
opencontext llm chat "Hello" --provider openrouter --model openrouter/auto
opencontext llm chat "Explain this code" --provider anthropic --model claude-sonnet-4-20250514
```

Supported providers: OpenRouter (100+ models), Anthropic (Claude), OpenAI (GPT), Local (Ollama/vLLM), Mock (default).

### Provider And Model Routing

OpenContext separates agent tools from LLM providers:

- Agent tools are surfaces such as Codex, Claude Code, OpenCode, Cursor, and Windsurf.
- LLM providers are model routes configured in `opencontext.yaml`.

The default route is `mock/mock-llm`, so setup, indexing, context packing, trace persistence,
doctor checks, and safety checks work without API keys. External provider calls are disabled by
default in core. If a host application adds a real provider adapter, it should do so outside
`opencontext_core`, update provider policy explicitly, and preserve redaction and trace controls.

For cost and security, prefer this order:

1. Use repo maps, symbol metadata, summaries, and selected snippets before full files.
2. Keep `max_tokens` task-specific instead of using the largest available window.
3. Use `plan` mode for architecture and scoping, `review` mode for implementation review,
   `audit` mode for security, and `implement_pack` only when exact snippets are needed.
4. Keep external providers disabled unless policy, classification, and approval allow them.
5. Store `trace_id` with model output so cost, source selection, and omitted context are auditable.

For service integrations, expose the FastAPI adapter and call:

```http
POST /v1/setup
POST /v1/context
GET /v1/traces/{trace_id}
```

Minimal setup request:

```json
{
  "root": ".",
  "write_config": true,
  "refresh_index": true
}
```

Minimal context request:

```json
{
  "query": "Review authentication",
  "root": ".",
  "max_tokens": 6000,
  "refresh_index": false
}
```

This creates the project harness files, writes safe model/agent policy documents, indexes the
project, builds a compact redacted context bundle, and persists the trace. The user does not need
to run `opencontext` commands for this path.

### What To Commit

Commit source code, reusable docs, tests, configs, and examples. Do not commit local runtime state
such as `.opencontext/`, `.storage/`, `.agents/`, virtualenvs, caches, trace files, or generated
analysis reports. The repository `.gitignore` excludes these by default. Reusable documentation
belongs under `docs/`; project-local harness files are recreated by `setup_project()`.

See [Runtime-First Setup](docs/getting-started/runtime-first.md) for a focused runtime integration
guide.

## Documentation Map

The root README is the starting point. From here, use the documentation by task:

- [Getting started](docs/getting-started/README.md): runtime-first setup, optional CLI install,
  first context pack, zero-key mode, and troubleshooting.
- [Concepts](docs/concepts/architecture.md): context engineering, repo maps, context packs,
  token budgets, memory, output budgets, technology profiles, and the controlled agentic harness.
- [Architecture](docs/architecture/overview.md): package boundaries, project intelligence,
  repo-map engine, context pack builder, safety layer, cache layer, workflow engine, evaluation,
  observability, and trace model.
- [Configuration](docs/configuration/overview.md): safe defaults and policy references for
  security, providers, tools, memory, output, cache, workflows, and templates.
- [Token efficiency](docs/token-efficiency/overview.md): repo-map-first packing, compression,
  prompt caching, content routing, compact serialization, memory savings, and output control.
- [Memory](docs/memory/overview.md): context repository, progressive disclosure, pinned memory,
  session harvesting, novelty gate, temporal memory, context DAG, and memory garbage collection.
- [Workflows](docs/workflows/overview.md): workflow packs, SDD flow, custom workflows, modes,
  validation, orchestration, and patch proposals.
- [Security](docs/security/threat-model.md): threat model, secret scanning, redaction, prompt
  injection, egress, provider policies, cache/memory isolation, tool security, MCP security, secure
  traces, and release artifact audit.
- [Quality](docs/quality/context-quality-evaluation.md): context quality evaluation, quality gates,
  ContextBench, plan drift detection, critic/verifier scaffolds, and tool-chain analysis.
- [Integrations](docs/integrations/python-sdk.md): Python SDK, API, CLI, Codex, Claude Code,
  Cursor, Windsurf, OpenCode/Kilo Code, DDEV, and GitHub Action integration notes.
- [Guides](docs/guides/agent-hints.md): agent hints, CI checks, git context, five-minute setup,
  and agent orchestration.
- [Profiles](docs/profiles/overview.md): generic, Python, Node/TypeScript, Drupal, Symfony, and
  profile authoring.
- [Operations](docs/operations/run-receipts.md): approvals, hooks, playbooks, shared commands,
  run receipts, policy diffs, org baselines, and AI-team operating model.
- [Enterprise](docs/enterprise/overview.md): air-gapped operation, evidence packs, governance
  reports, retention, org baselines, and team policies.
- [Development](docs/development/contributing.md): architecture boundaries, testing, adding
  commands, serializers, profiles, and memory backends.
- [Roadmap](docs/roadmap.md) and [release checklist](docs/release-checklist.md): current direction
  and release validation.

The same map is available as a docs-only index in [docs/README.md](docs/README.md).

## Optional CLI Quickstart

Install the CLI only when you want explicit terminal commands:

```bash
pip install opencontext-cli
cd your-project
opencontext onboard
opencontext index .
opencontext pack . --query "Review authentication" --mode plan --copy
```

CLI commands map directly to the runtime-first APIs:

| CLI command | Runtime/API equivalent |
| --- | --- |
| `opencontext onboard` | `runtime.setup_project(...)` or `POST /v1/setup` |
| `opencontext index .` | `runtime.index_project(...)` |
| `opencontext pack . --query ...` | `runtime.prepare_context(...)` or `POST /v1/context` |
| `opencontext trace last` | `runtime.latest_trace()` |

Use the CLI for manual onboarding, doctor checks, one-off context packs, memory commands, token
reports, release checks, and evidence reports. Product integrations should prefer the runtime/API
path so users do not need to run OpenContext commands before the integration works.

See [Optional CLI Installation](docs/getting-started/cli-installation.md) for CLI-specific details.

Editable development install:

```bash
pip install -e packages/opencontext_core -e packages/opencontext_profiles -e packages/opencontext_providers -e packages/opencontext_cli -e packages/opencontext_api
```

## Zero-Key Mode

First run works without API keys. The default provider is `mock/mock-llm`, so indexing, repo maps, context packs, memory commands, token reports, prompt audit, release audit, doctor checks, and governance scaffolds run locally.

Recommended runtime path:

```python
from opencontext_core import OpenContextRuntime

runtime = OpenContextRuntime()
runtime.setup_project(".")
prepared = runtime.prepare_context("Explain this project", max_tokens=6000)
```

Recommended CLI path:

```bash
opencontext onboard
opencontext doctor
opencontext index .
opencontext pack . --query "Explain this project"
```

## Safe By Default

- External providers disabled by default.
- Tools disabled by default.
- MCP disabled by default.
- Network denied by default.
- Filesystem write actions denied by default.
- Raw traces disabled by default.
- Semantic cache disabled by default.
- Secrets are redacted before prompts, traces, cache, memory, repo maps, and context packs.
- Air-gapped mode blocks external providers, MCP, and external telemetry.
- Missing provider policy fails closed.

## Basic Commands

```bash
opencontext init --template generic
opencontext init --template drupal
opencontext init --template enterprise
opencontext init --template air-gapped
opencontext onboard
opencontext doctor security
opencontext index .
opencontext inspect repomap --format toon
opencontext pack . --query "review auth" --format markdown --copy
opencontext pack . --query "review auth" --format json
opencontext pack . --query "review auth" --format toon
opencontext ask "Summarize project" --output-mode technical_terse
opencontext trace last --format compact_table
opencontext tokens report
opencontext memory init
opencontext memory search "access control"
opencontext agent init --target cursor
opencontext agent init --target windsurf
opencontext prompt audit .
opencontext prompt sbom --trace last
opencontext release audit --dist dist/
opencontext release evidence --dist dist/
opencontext cache plan --query "review auth"
opencontext evidence pack --output-mode report
```

## Knowledge Graph Commands

OpenContext includes a full code knowledge graph with SQLite+FTS5, call graph analysis, impact analysis, and framework route detection:

```bash
# Index a project into the knowledge graph
opencontext index .

# Search for symbols
opencontext knowledge-graph search "authenticate" --limit 20
opencontext knowledge-graph query "user" --kind function

# Build context for a task
opencontext knowledge-graph context "implement auth" --max-nodes 20

# Trace call relationships
opencontext knowledge-graph callers "authenticate_user" --depth 2
opencontext knowledge-graph callees "authenticate_user" --depth 2

# Analyze change impact
opencontext knowledge-graph impact "authenticate_user" --radius 2

# Check index status
opencontext knowledge-graph status
```

## Installation & Setup

OpenContext provides a complete installation management system for agent configuration:

```bash
# Install with interactive wizard
opencontext setup install

# Install specific profile
opencontext setup install --profile full
opencontext setup install --profile minimal
opencontext setup install --profile agents-only

# Install for specific agents
opencontext setup install --target claude,opencode,cursor

# Install specific components
opencontext setup install --component mcp --component agents

# Update installation
opencontext setup update
opencontext setup update --check-only

# Verify installation health
opencontext setup verify

# Show installation status
opencontext setup status

# Uninstall (keeps backups by default)
opencontext setup uninstall
opencontext setup uninstall --keep-backups
```

### Installation Profiles

- **minimal**: MCP server config only
- **full**: All components (MCP, agents, skills, profiles, hooks, docs)
- **agents-only**: Only AI agent configurations
- **mcp-only**: Only MCP server configuration
- **custom**: User-selected components

### Agent Installer

Install OpenContext integration for your favorite AI agents:

```bash
# Auto-detect installed agents
opencontext install

# Install specific agents
opencontext install --target claude,opencode,cursor

# Local (project-only) install
opencontext install --location local
```

Supported agents: Claude Code, OpenCode, Kilo Code, Gemini CLI, Cursor, VS Code Copilot, Codex, Windsurf, Antigravity, Kimi Code, Kiro IDE, Qwen Code, OpenClaw, Pi.

## MCP Server

Start the MCP server for agent integration:

```bash
# Stdio transport (for Claude Code, Cursor, etc.)
opencontext serve --mcp
```

Available MCP tools:
- `opencontext_search` - Find symbols by name
- `opencontext_context` - Build relevant code context
- `opencontext_callers` - Trace callers
- `opencontext_callees` - Trace callees
- `opencontext_impact` - Analyze change impact
- `opencontext_node` - Get symbol details
- `opencontext_files` - List indexed files
- `opencontext_status` - Check index health

## Git Context

Enrich knowledge graph queries with git history and authorship:

```bash
# Show repository stats
opencontext git status

# Show git history for a file
opencontext git history src/auth.py

# Show recent changes
opencontext git recent --days 7 --max-commits 20

# Show blame for specific lines
opencontext git blame src/auth.py --start 10 --end 25
```

Git context integrates with the knowledge graph to provide additional metadata such as last author, commit count, and recent change history when building AI task context.

## CI Checks

Define and run automated code checks enforceable in CI:

```bash
# Initialize checks directory with samples
opencontext ci-check init

# List discovered checks
opencontext ci-check list

# Run all checks
opencontext ci-check run

# Run checks on a specific file
opencontext ci-check run --file src/auth.py

# Create a new check template
opencontext ci-check create "API Validation"
```

Checks are defined as markdown files in `.opencontext/checks/` with YAML frontmatter:

```markdown
---
name: Security Review
description: Review for security issues
severity: error
files:
- "*.py"
patterns:
- "password\\s*="
- "secret\\s*="
---
Review this code for security issues.
```

## Agent Hints

Provide project-specific instructions to AI agents via `.opencontexthints`:

```bash
# Initialize hints file
opencontext hints init

# Show combined hints from all sources
opencontext hints show

# Validate hints files
opencontext hints validate
```

The `.opencontexthints` file defines conventions, architecture, workflows, patterns, and warnings:

```
project: My Project

[conventions]
- Use type hints for all function signatures
- Prefer dataclasses over dicts

[architecture]
- Core business logic is in the domain layer
- Infrastructure concerns are in adapters

[workflows]
- Run the full test suite before committing

[patterns]
- Repository pattern for data access

[warnings]
- Never commit secrets or API keys
```

Also supports `AGENTS.md`, `CLAUDE.md`, and agent-specific rule files.

## Affected Tests

Find which tests are affected by code changes:

```bash
# From changed files
opencontext affected src/auth.py src/utils.py

# From git diff
git diff --name-only | opencontext affected --stdin

# With custom filter
opencontext affected src/auth.py --filter "*e2e*"

# Output only file paths
opencontext affected src/auth.py --quiet
```

## SDD Workflow

Run Spec-Driven Development workflows:

```bash
# Initialize SDD context
opencontext sdd explore "how does auth work?"

# Create proposal
opencontext sdd propose "implement OAuth"

# Run complete flow
opencontext sdd flow "implement OAuth" --max-tokens 6000
```

## Token Efficiency

OpenContext reduces input and output waste with:

- Repo map first: paths and symbols before raw file snippets.
- Symbol/path retrieval and deterministic ranking.
- Optional local deterministic embeddings and cross-project graph tunnels for recall, still behind
  core interfaces and policy.
- Context packing with token budgets and omission reasons.
- Adaptive/protected compression.
- MCP/tool response compression boundary for future adapters.
- Output budgets and output modes.
- Cache-aware prompt prefix planning.
- Progressive disclosure memory.
- Compact table serialization for structured metadata.

Token savings are measurable with:

```bash
opencontext tokens report .
opencontext pack . --query "How does context packing work?" --format markdown
opencontext pack . --query "How does context packing work?" --format toon
opencontext trace last
```

OpenContext does not claim lossless compression unless exact reconstruction or source expansion is available.

## Memory

The memory layer is local, redacted, classification-aware, and progressive:

- `layer_0`: pinned critical context.
- `layer_1`: compact summaries.
- `layer_2`: searchable facts.
- `layer_3`: expandable original sources.
- Context repository search uses traceable multi-signal scoring across keyword overlap, entity-like
  metadata, priority, recency, pinned state, and agent-generated facts.
- Temporal memory and context DAG scaffolds preserve validity, supersession, provenance, and
  expandable source references.

Memory is stored under `.opencontext/context-repository/` with frontmatter metadata for id, kind, classification, priority, pinning, provenance, validity, token estimate, and pruning state.

```bash
opencontext memory init
opencontext memory list
opencontext memory search "access control"
opencontext memory expand <memory_id>
opencontext memory pin <memory_id>
opencontext memory harvest --from-trace last
opencontext memory prune
opencontext memory facts
```

Automatic harvesting is disabled by default. Harvested memory requires approval by default and stores redacted summaries, not raw traces.

## Context Packs

Context packs include selected sources, token stats, security warnings, included context, and omitted context reasons. Retrieved content is marked as untrusted and cannot override system, developer, policy, or workflow instructions.

```bash
opencontext pack . --query "Review authentication" --mode review --max-tokens 6000
```

Use context packs with Codex, Cursor, Claude Code, OpenCode, Kilo Code, Cline, Roo, Windsurf, or another coding agent by copying the generated pack into the agent session.

## Agent Tool Integrations

OpenContext is designed to be agent-tool neutral. It generates small project-local instruction files that tell an agent to request minimal redacted context instead of reading the whole repository.

```bash
# Generic/Codex/OpenCode-compatible instructions.
opencontext agent init --target generic

# OpenCode: creates AGENTS.md and opencode.json.
opencontext agent init --target opencode

# Claude Code: creates CLAUDE.md.
opencontext agent init --target claude-code

# Cursor: creates .cursor/rules/opencontext.mdc.
opencontext agent init --target cursor

# Windsurf: creates .windsurf/rules/opencontext.md.
opencontext agent init --target windsurf

# Kilo Code / OpenClaw style AGENTS.md.
opencontext agent init --target kilo-code
opencontext agent init --target openclaw
```

For one-off sessions, generate a compact agent context block:

```bash
opencontext agent-context "Review access control" --target codex --copy
opencontext agent-context "Review access control" --target claude-code --copy
opencontext agent-context "Review access control" --target cursor --copy
opencontext agent-context "Review access control" --target windsurf --copy
```

Recommended agent workflow:

1. Run `opencontext onboard`.
2. Run `opencontext doctor security`.
3. Generate the integration file for your tool.
4. Ask the agent to run `opencontext pack . --query "<task>" --mode plan --copy`.
5. Paste or reference the resulting context pack in the agent session.

The generated files are intentionally boring: they contain no secrets, no hidden prompts, and no provider credentials. They only document safe OpenContext commands and deny-by-default expectations.

Reference wrappers are available under
[examples/agent-wrappers](examples/agent-wrappers/README.md). They show the
runtime-first pattern for Codex, Claude Code, OpenCode, and provider-neutral
custom adapters without adding provider SDK dependencies to core.

## Modes And Workflows

Context modes shape the pack:

- `plan`: signatures, summaries, dependencies.
- `review`: diffs, affected symbols, related tests.
- `audit`: security relevant code, config, tests.
- `implement_pack`: exact snippets/files and tests.

Core workflow execution exists for `code_assistant`. Many team workflows are scaffolded and honestly print policy/token/approval plans without unsafe side effects:

```bash
opencontext workflow dry-run security-audit
opencontext run architect --task "Review auth boundaries"
opencontext propose patch --task "Fix access resolver tests"
```

The controlled harness planner models each turn before native execution: preprocessing,
LLM streaming, error recovery, tool execution, and continuation checks. It can request compaction
from token-ratio thresholds, stop at maximum turn limits, and evaluate proposed tool calls through
the same read/write/network permission pipeline used by the native tool registry. Native tool
execution remains disabled by default.

## Technology Profiles And Templates

Core remains universal. Technology Profiles provide stack-specific hints without importing frameworks into core.

Templates include `generic`, `drupal`, `symfony`, `python`, `node`, `typescript`, `enterprise`, `air-gapped`, and `ci`.

```bash
opencontext init --template python
opencontext init --template drupal
opencontext validate --profile drupal
```

Prebuilt config overlays live in `configs/`.

## Configuration

Most users should run `opencontext onboard` and keep the safe defaults:

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

Advanced docs:

- [Configuration reference](docs/configuration/reference.md)
- [Security policy](docs/configuration/security-policy.md)
- [Provider policy](docs/configuration/provider-policy.md)
- [Tool policy](docs/configuration/tool-policy.md)
- [Memory policy](docs/configuration/memory-policy.md)
- [Output policy](docs/configuration/output-policy.md)
- [Technology profiles](docs/profiles/overview.md)

## AI Leak Security And Team Operations

OpenContext assumes prompts, configs, source maps, traces, memory files, and release artifacts can leak. It includes local implementations and scaffolds for prompt auditing, release auditing, output exfiltration scanning, egress policy, cache planning, cost ledgers, quality gates, plan drift detection, tool-chain analysis, playbooks, persistent local approvals, run receipts, prompt/context SBOMs, release evidence, workflow-pack integrity signing, and policy diffs.

```bash
opencontext prompt audit .
opencontext prompt sbom --trace last --output .opencontext/reports/prompt-context-sbom.json
opencontext release gate
opencontext release evidence --dist dist/
opencontext approvals list
opencontext approvals request --kind provider_use --reason "Use approved private endpoint"
opencontext run receipt last
opencontext quality preflight --query "review auth"
```

These are local guardrails and scaffolds today; they do not make the project a fully certified enterprise platform.

## Validation

```bash
pytest
ruff check .
ruff format --check .
mypy packages/opencontext_core
python -m build packages/opencontext_core
python -m build packages/opencontext_profiles
python -m build packages/opencontext_providers
python -m build packages/opencontext_cli
python -m build packages/opencontext_api
opencontext --help
opencontext memory --help
opencontext pack --help
```

Before publishing, use the [release checklist](docs/release-checklist.md).

## Public Context Benchmarks

Use ContextBench to prove the narrow claim OpenContext controls: expected source
coverage under a token budget with measurable reduction against the indexed
project baseline.

```bash
opencontext eval contextbench examples/evals/contextbench.yaml \
  --root . \
  --max-tokens 6000 \
  --min-token-reduction 0.50
```

The benchmark fails when expected source fragments are missing, forbidden source
fragments are included, or token reduction drops below the configured threshold.
It does not claim that a downstream LLM answer is semantically perfect; model
answer quality needs provider-specific evals on top of this layer.

## Current Implementation Status

Implemented:

- Local project indexing, repo maps, retrieval, ranking, context packing.
- **Code knowledge graph** with SQLite+FTS5, call graph analysis, impact analysis, and framework route detection (19+ languages).
- **Context builder** for AI tasks using knowledge graph search and call graph traversal.
- **Affected test finder** tracing dependencies to identify tests impacted by changes.
- **MCP stdio server** exposing 8 tools for agent integration.
- **Agent installer** supporting 13+ AI coding agents with auto-detection and config generation.
- **SDD orchestrator** with 7-phase lifecycle, artifact stores (engram/openspec/hybrid), DAG state tracking, and per-phase model assignment.
- **Skill registry** with auto-discovery, compact rules extraction, and context-aware resolution.
- **Engram-style memory extensions** with topic keys, session summaries, and proactive save triggers.
- Static dependency graph extraction, optional cross-project graph tunnel storage, and local
  deterministic embedding records behind core interfaces.
- Secret scanning and sink redaction.
- Provider policy enforcement and context firewall checks.
- Cache-friendly prompt assembly.
- Local JSON traces.
- OutputBudgetController and output modes.
- ContentRouter and deterministic serializers for markdown/json/yaml/toon/compact_table.
- Progressive memory repository, multi-signal memory search, pinning, expansion, harvesting,
  novelty gate, temporal graph, context DAG, compression quality gate, and GC scaffold.
- Controlled harness preflight planner and traceable tool permission pipeline.
- Prebuilt safe configs and onboarding workspace.
- Prompt/release/output leak scanners and team/performance/quality scaffolds.
- Persistent local approval inbox under `.opencontext/approvals`.
- Optional provider adapter package outside core (`opencontext_providers`) with mock adapter and external-provider scaffold.
- Local HMAC workflow-pack integrity signatures with `opencontext packs sign` and `opencontext packs verify`.
- Context quality evaluator for context packs and traces.
- Release evidence artifacts with file hashes and release-audit findings.
- Prompt/context SBOM artifacts with prompt/context/policy hashes and selected source refs.
- Agent integration file generator for generic/Codex/OpenCode/Claude Code/Cursor/Windsurf/Kilo Code/OpenClaw.

Scaffolded:

- Native tool execution, real provider SDK adapters, provider explicit caches,
  org baseline enforcement, release transparency logs, public-key signed workflow packs, sandbox
  execution, critic/verifier model calls, prompt/context SBOM signing, and enterprise governance
  dashboards.

Not implemented:

- Real external provider calls in core.
- Vector databases.
- Hosted multi-user policy service.
- Full enterprise certification.

## Roadmap

See [docs/roadmap.md](docs/roadmap.md). Near milestones now move toward parser-backed dependency graphs, provider SDK packages behind explicit policy, public-key workflow-pack signing, richer context quality evaluation, reproducible release evidence, signed prompt/context SBOMs, and sandboxed execution environments.

## Security Warning

Do not put secrets in GitHub issues, prompts, traces, examples, configs, test fixtures, workflow packs, or memory files. If you find a vulnerability, follow [SECURITY.md](SECURITY.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [development docs](docs/development/contributing.md). Keep core technology-agnostic, preserve safe defaults, add tests for security-sensitive behavior, and be explicit when a feature is scaffolded rather than complete.
