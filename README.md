<p align="center">
  <img src="docs/assets/logo.svg" alt="OpenContext" width="160" height="160">
</p>

<p align="center">
  <b>Your AI agent reads 95,000 tokens per query. OpenContext sends 3,500.</b><br>
  <sub>Context engineering · Semantic knowledge graph · SDD workflow · Zero secrets · Works offline</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/87%25_token_reduction-measured-00C9A7" alt="87% token reduction">
  <img src="https://img.shields.io/badge/offline--first-no_API_key_needed-00A8E8?logo=python&logoColor=white" alt="Works offline">
  <img src="https://img.shields.io/badge/13%2B_agents-Claude_%7C_Cursor_%7C_Copilot-845EC2" alt="13+ agents">
  <img src="https://img.shields.io/badge/license-MIT-gray" alt="MIT">
</p>

<p align="center">
  <a href="#-quick-start"><b>Get started →</b></a> &nbsp;·&nbsp;
  <a href="#benchmark">Benchmark</a> &nbsp;·&nbsp;
  <a href="#feature-overview">Features</a> &nbsp;·&nbsp;
  <a href="#agent-integration">Agents</a> &nbsp;·&nbsp;
  <a href="#python-sdk">SDK</a>
</p>

---

```sh
$ opencontext pack . --query "How does authentication work?" --copy

  Indexing   ━━━━━━━━━━━━━━━━━━━━  231 files   0.3s
  Matching   ████████░░░░░░░░░░░░  12 / 231    semantic rank
  Redacting  ━━━━━━━━━━━━━━━━━━━━  0 secrets   clean
  Budget     ████████░░░░░░░░░░░░  3,421 tok   ↓ 87%

  ✓ Copied to clipboard
    95,000 → 3,421 tokens  ·  $0.28 → $0.01 per query
```

---

<table>
<tr>
<th>Without OpenContext</th>
<th>With OpenContext</th>
</tr>
<tr>
<td>

```
src/auth.py
src/models.py
src/routes.py     ← all 231 files
src/views.py
tests/ (50 files)
docs/ (20 files)
...161 more files

95,000 tokens · $0.28/query
```

</td>
<td>

```
src/auth.py      ✓ relevant
src/models.py    ✓ relevant
─────────────────────────────

3,421 tokens · $0.01/query
secrets redacted · auditable
```

</td>
</tr>
</table>

| | Naive | Keyword grep | **OpenContext** |
|---|---:|---:|---:|
| Tokens sent | ~95,000 | ~15,000 | **~3,500** |
| Cost / query | ~$0.28 | ~$0.04 | **~$0.01** |
| Secrets in prompt | ⚠️ Possible | ⚠️ Possible | ✅ Redacted |
| Cross-file deps | ❌ Missed | ❌ Missed | ✅ Traced |
| Auditable | ❌ | ❌ | ✅ Full trace |

---

## ⚡ Quick Start

```bash
# Install (once)
curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh | bash

# Set up your project — auto-detects stack, tools, agents
cd your-project && opencontext install --yes

# Get a task-specific context pack, copied to clipboard
opencontext pack . --query "How does authentication work?" --copy
```

> **No API keys. No external services.** Context packs, knowledge graph, memory, and SDD workflow run fully offline from the first command.

**Prefer an interactive setup?**
```bash
opencontext config wizard
```

---

## How It Works

```
Your codebase
     │
     ▼
┌─────────────────────────────┐
│  1. Index                   │  opencontext index .
│  SQLite + FTS5 knowledge    │  → symbols, call graph, imports,
│  graph with call analysis   │    framework routes, bridges
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  2. Query                   │  opencontext pack . --query "task"
│  Semantic retrieval ranked  │  → top-K files by relevance score
│  by task relevance          │    across symbols + call graph
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  3. Optimize                │  Automatic, every time
│  Compress, redact secrets,  │  → token budget enforced
│  enforce token budget        │    PII stripped, no leaks
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  4. Deliver                 │  Clipboard / file / API / MCP
│  Compact context pack for   │  → your agent works smarter,
│  your AI agent              │    not harder
└─────────────────────────────┘
```

---

## Benchmark

Reproducible. Run it yourself:

```bash
python -m pytest tests/core/test_comparative_benchmark.py -v -s
```

| Task | Difficulty | Naive tokens | OpenContext | Reduction | SDD | TDD | Secrets |
|---|---|---:|---:|---:|---|---|---|
| Add method to BridgeDetector | Simple | 38,381 | 2,482 | **93.5%** | ✓ | ✓ | Clean |
| Add --json flag to CLI command | Medium | 38,188 | 2,145 | **94.4%** | ✓ | ✓ | Clean |
| Wire tracing to WorkflowEngine | Hard | 24,636 | 6,509 | **73.6%** | ✓ | ✓ | Clean |
| **Average** | | | | **87.2%** | 3/3 | 3/3 | 3/3 |

*Methodology: naive baseline = all files in the relevant directory. Token estimate: `len(text) / 4`.*

---

## Feature Overview

### Knowledge Graph

Indexes your project into a queryable SQLite graph. No external vector DB, no embeddings service.

```bash
opencontext index .

opencontext knowledge-graph search "authenticate"        # Find symbols
opencontext knowledge-graph callers "authenticate_user"  # Who calls this
opencontext knowledge-graph impact "UserModel" --radius 2  # What breaks if I change this
opencontext knowledge-graph view --format tree           # Visual project structure
```

**Framework-aware routing** — detects URL-to-handler mappings for Django, FastAPI, Flask, Express, and NestJS:

```bash
opencontext routes scan .                    # All frameworks
opencontext routes scan . --framework fastapi  # FastAPI only
opencontext routes scan . --json             # Machine-readable
```

**Cross-language bridge detection** — HTTP calls, gRPC stubs, subprocesses, IPC across `.py`, `.ts`, `.go`, `.rs`, and more:

```bash
opencontext bridges scan .                  # All bridges
opencontext bridges scan . --type GRPC      # gRPC only
opencontext bridges scan . --json           # Machine-readable
```

---

### Spec-Driven Development (SDD)

An 8-phase governance harness that keeps AI agents disciplined:

```
explore → propose → spec → design → tasks → apply → verify → archive
```

The harness creates the run structure, enforces token budgets and quality gates, persists artifacts, and runs verification. Your AI agent (Claude Code, Cursor, etc.) executes each phase using the context pack. Nothing ships without passing `verify`.

```bash
# Create governance scaffolding + index the project
opencontext harness run --workflow sdd --task "Add OAuth2 login"
opencontext harness list

# Sync tasks to GitHub Issues
opencontext sync issues --change my-feature --dry-run
opencontext sync issues --change my-feature
```

**SDD enforces:**
- Per-phase token budgets and quality gates
- Structured artifacts: context-pack, proposal, apply-manifest, verify-report
- Test run with pass/fail counts at every verify phase
- Archive trail for every completed change

**Pair with your agent:** `opencontext agent init --target claude-code` generates a `CLAUDE.md` with phase-by-phase instructions so your agent knows exactly what to do at each step.

---

### Workflow Presets

Apply named configuration modes in one command:

```bash
opencontext preset list

opencontext preset apply fast        # Cheap model, 2K token budget — fast iteration
opencontext preset apply deep        # Premium model, 8K budget — maximum quality
opencontext preset apply privacy     # Air-gapped, no external providers, fail-closed
opencontext preset apply strict-tdd  # Enforce strict test-first discipline
opencontext preset apply air-gapped  # Completely offline
```

| Preset | Model | Token budget | Use case |
|---|---|---|---|
| `fast` | cheap | 2K / 600 | Quick iteration |
| `deep` | premium | 8K / 2K | Architecture work |
| `privacy` | any (local) | default | Sensitive codebases |
| `strict-tdd` | any | default | High-stakes changes |
| `air-gapped` | local | default | Enterprise / offline |

Add custom presets in `.opencontext/presets/my-preset.yaml`.

---

### Party Mode Review

Multi-perspective code review with independent LLM reviewers:

```bash
# With a configured provider (ANTHROPIC_API_KEY or OPENROUTER_API_KEY)
opencontext review --party --context "$(git diff HEAD~1)"

# Select specific roles
opencontext review --party --roles "architect,security" --context "$(cat pr.diff)"

# Save report to file
opencontext review --party --context "$(cat changes.py)" --output review.md
```

Four independent reviewers — **architect**, **security**, **performance**, **ux** — each focused on their domain, findings aggregated by severity.

---

### Extensions

```bash
opencontext extension search              # Browse 7 built-in extensions
opencontext extension search review       # Filter by keyword
opencontext extension install strict-review
opencontext extension list
opencontext extension remove strict-review
```

| Extension | Description |
|---|---|
| `strict-review` | Multi-reviewer SDD review phase |
| `gh-issues-tracker` | Sync SDD tasks to GitHub Issues |
| `cost-guard` | Block phases that exceed token budget |
| `framework-router` | Framework-aware URL routing detection |
| `party-review` | 4-role LLM review with findings aggregation |
| `token-telemetry` | Cumulative token savings tracking |
| `bridge-detector` | Cross-language call boundary detection |

---

### Token Telemetry

Track cumulative savings over time:

```bash
opencontext telemetry show           # Cumulative savings
opencontext telemetry show --last 10 # Recent events only
opencontext telemetry clear
```

---

### Safety — Secure by Default

OpenContext ships with a deny-by-default posture:

- **External providers** — disabled by default
- **MCP tools** — disabled by default, allowlist required
- **Network** — denied by default
- **Secrets** — redacted before every prompt, trace, cache entry, and context pack
- **Raw traces** — disabled by default
- **Missing policy** — fails closed, not open

```bash
opencontext preset apply privacy     # Maximum privacy mode
opencontext doctor security          # Security audit
```

**Zero-key mode** — context packs, repo maps, knowledge graph, memory, and SDD work entirely offline.

---

## CLI Reference

### Setup

```bash
opencontext install           # Auto-detect & configure (cross-platform)
opencontext install --yes     # Non-interactive (CI-friendly)
opencontext index .           # Index project
opencontext doctor            # Health check
opencontext doctor deep       # Deep runtime diagnostics
opencontext update            # Check for updates
opencontext upgrade           # Upgrade all packages
```

### Context & Knowledge Graph

```bash
opencontext pack . --query "task" --copy         # Context to clipboard
opencontext pack . --query "task" --format json  # JSON output

opencontext knowledge-graph search "symbol"
opencontext knowledge-graph callers "func_name"
opencontext knowledge-graph callees "func_name"
opencontext knowledge-graph impact "ClassName" --radius 2
opencontext knowledge-graph view                 # Mermaid graph (opens browser)
opencontext knowledge-graph view --format tree   # Rich directory tree
```

### SDD / Workflow

```bash
opencontext harness run --workflow sdd --task "description"
opencontext harness list
opencontext sync issues --change <name> --dry-run
opencontext workflow resume <run-id>
```

### Analysis

```bash
opencontext bridges scan . --type HTTP --json
opencontext bridges show <symbol>
opencontext routes scan . --framework fastapi
opencontext review --party --context "$(git diff HEAD~1)"
```

### Configuration

```bash
opencontext config wizard
opencontext config show
opencontext preset list
opencontext preset apply <name> --dry-run
opencontext preset apply <name>
```

### Benchmark

```bash
opencontext benchmark run              # Run all quality checks
opencontext benchmark run --format json
opencontext benchmark compare          # Compare against last baseline
opencontext telemetry show
```

### Plugins & Extensions

```bash
opencontext plugin search
opencontext plugin install <name>
opencontext extension search
opencontext extension install <name>
```

### Memory

Store, search, and manage context memory items across sessions.

```bash
opencontext memory init              # Initialize context repository
opencontext memory list              # List stored memory items
opencontext memory search "query"    # Search memory
opencontext memory show <id>         # Show item details
opencontext memory pin <id>          # Pin important item
opencontext memory harvest           # Extract memories from last trace
opencontext memory gc                # Garbage collect stale items
```

### One-off Context Blocks

Generate a safe, redacted context block for any AI agent.

```bash
opencontext agent-context "Implement rate limiting" --target cursor --copy
opencontext agent-context "Review auth module" --target claude-code --copy
```

---

## Agent Integration

OpenContext is agent-neutral. It generates a small instruction file that tells your agent to use the knowledge graph instead of reading files directly.

| Agent | Generated file |
|---|---|
| Claude Code | `CLAUDE.md` |
| OpenCode | `AGENTS.md` + `opencode.json` |
| Cursor | `.cursor/rules/opencontext.mdc` |
| Windsurf | `.windsurf/rules/opencontext.md` |
| Codex / Generic | `AGENTS.md` |
| Kilo Code | `AGENTS.md` |

```bash
opencontext agent init --target claude-code
opencontext agent init --target cursor
opencontext agent init --target opencode

# One-off context block
opencontext agent-context "Implement rate limiting" --target cursor --copy
```

**MCP server** — 8 tools for agents that support the Model Context Protocol:

```bash
opencontext mcp    # Start MCP server on stdio
```

Tools: `opencontext_search`, `opencontext_context`, `opencontext_callers`, `opencontext_callees`, `opencontext_impact`, `opencontext_node`, `opencontext_files`, `opencontext_status`

---

## Python SDK

```python
from opencontext_core import OpenContextRuntime

runtime = OpenContextRuntime()
runtime.setup_project(".")
prepared = runtime.prepare_context("Review authentication", max_tokens=6000)

# prepared.context   → compact, redacted, task-specific markdown
# prepared.trace_id  → auditable record of what was included and why
```

---

## Default Configuration

```yaml
security:
  mode: private_project
  fail_closed: true
models:
  default:
    provider: mock      # swap for anthropic / openrouter / openai / local
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
  require_approval: true
  store_raw: false
```

---

## Documentation

| Topic | Links |
|---|---|
| **Getting Started** | [Quickstart](docs/getting-started/quickstart.md) · [CLI Install](docs/getting-started/cli-installation.md) · [Troubleshooting](docs/getting-started/troubleshooting.md) |
| **Architecture** | [Overview](docs/architecture/overview.md) · [Context Pack Builder](docs/architecture/context-pack-builder.md) · [Safety Layer](docs/architecture/safety-layer.md) |
| **SDD Workflow** | [SDD Guide](docs/workflows/sdd-workflow.md) · [Custom Workflows](docs/workflows/custom-workflows.md) · [Workflow Packs](docs/workflows/workflow-packs.md) |
| **Configuration** | [Reference](docs/configuration/reference.md) · [Security Policy](docs/configuration/security-policy.md) · [Provider Policy](docs/configuration/provider-policy.md) |
| **Security** | [Threat Model](docs/security/threat-model.md) · [Data Classification](docs/security/data-classification.md) · [Prompt Security](docs/security/ai-leak-and-prompt-security.md) |
| **Integrations** | [Python SDK](docs/integrations/python-sdk.md) · [API](docs/integrations/api.md) · [GitHub Action](docs/integrations/github-action.md) |
| **Enterprise** | [Air-Gapped](docs/enterprise/air-gapped.md) · [Governance Reports](docs/enterprise/governance-reports.md) |
| **Development** | [Contributing](docs/development/contributing.md) · [Testing](docs/development/testing.md) |

---

## Validation

```bash
pytest                          # 866 tests
ruff check .                    # Lint
ruff format --check .           # Format
mypy packages/opencontext_core  # Types
python -m pytest tests/core/test_comparative_benchmark.py -v -s  # Benchmark
```

---

## Install

| Method | Command |
|---|---|
| pip | `pip install opencontext-cli` |
| One-liner (Linux/macOS) | `curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh \| bash` |
| One-liner (Windows) | `irm https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.ps1 \| iex` |
| Source | `git clone … && pip install -e packages/*` |

Requires **Python 3.12+**. No API keys required for core functionality.

---

## License

MIT — see [LICENSE](LICENSE).

**Security:** Never put secrets in prompts, traces, examples, configs, or memory files. Report vulnerabilities via [SECURITY.md](SECURITY.md).

**Contributing:** See [CONTRIBUTING.md](CONTRIBUTING.md).
