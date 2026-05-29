<p align="center">
  <img src="docs/assets/logo.svg" alt="OpenContext" width="120" height="120">
</p>

<h2 align="center">OpenContext Runtime</h2>

<p align="center">
  <b>Your AI agent reads the whole project. OpenContext sends only what matters.</b><br>
  <sub>Context engineering · Semantic knowledge graph · SDD workflow · Zero secrets · Works offline</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/up_to_96%25_token_reduction-benchmarked-00C9A7?style=flat-square" alt="Up to 96% token reduction">
  <img src="https://img.shields.io/badge/offline--first-no_API_key-00A8E8?style=flat-square&logo=python&logoColor=white" alt="Works offline">
  <img src="https://img.shields.io/badge/13%2B_agents-Claude_%7C_Cursor_%7C_Copilot-845EC2?style=flat-square" alt="13+ agents">
  <img src="https://img.shields.io/badge/tests_passing-00C9A7?style=flat-square" alt="Tests">
  <img src="https://img.shields.io/badge/license-MIT-gray?style=flat-square" alt="MIT">
</p>

<p align="center">
  <a href="#-quick-start"><b>Quick Start</b></a> &nbsp;·&nbsp;
  <a href="#using-with-your-agent">Agents</a> &nbsp;·&nbsp;
  <a href="#how-it-works">How It Works</a> &nbsp;·&nbsp;
  <a href="#feature-overview">Features</a> &nbsp;·&nbsp;
  <a href="#benchmark">Benchmark</a> &nbsp;·&nbsp;
  <a href="#python-sdk">SDK</a> &nbsp;·&nbsp;
  <a href="#cli-reference">CLI</a>
</p>

---

```sh
$ opencontext pack . --query "How does authentication work?" --copy

  Indexing   ━━━━━━━━━━━━━━━━━━━━  385 files   0.4s
  Matching   ████████░░░░░░░░░░░░  11 / 385    call graph rank
  Redacting  ━━━━━━━━━━━━━━━━━━━━  0 secrets   clean
  Budget     ████████░░░░░░░░░░░░  3,421 tok   ↓ 96%

  ✓ Copied to clipboard
    full project → 3,421 tokens  ·  only relevant symbols
```

---

## ⚡ Quick Start

**Install once, then set up each project in one command:**

```bash
# Install OpenContext
pip install opencontext-cli
# Linux/macOS:
curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh | bash
# Windows PowerShell:
irm https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.ps1 | iex
```

```bash
# Set up your project
cd your-project
opencontext install
```

`opencontext install` does everything automatically:

1. **Detects your stack** — Python, Node, Go, Rust, Terraform, and 200+ profiles
2. **Builds the knowledge graph** — symbols, call chains, imports, framework routes
3. **Configures your agent** — generates the right instruction file for your editor
4. **Sets up MCP tools** — pre-approves 8 knowledge graph tools if your agent supports MCP
5. **Verifies the setup** — runs a health check before finishing

> **No API keys. No external services.** The knowledge graph, memory, and SDD workflow run fully offline.

**Then get your first context pack:**

```bash
opencontext pack . --query "How does authentication work?" --copy
# → Copies a 3,500-token task-specific context pack to your clipboard
# Paste it into your agent chat and start asking.
```

**Prefer to configure interactively?**

```bash
opencontext config wizard   # Step-by-step configuration
opencontext doctor          # Verify everything is healthy
```

---

## Using with Your Agent

OpenContext is agent-neutral. After `opencontext install`, your agent is already configured. Below is how to use it day-to-day with each supported agent.

---

### OpenCode

`opencontext install` installs three things into `~/.config/opencode/`:

| File | Purpose |
|---|---|
| `mcp.json` | Registers all 8 OpenContext MCP tools |
| `AGENTS.md` | Agent instructions for using the knowledge graph |
| `agents/sdd-orchestrator.json` | SDD orchestrator agent profile |

**Day-to-day workflow:**

```
1. Open your project in OpenCode
2. Press Tab to switch to the sdd-orchestrator agent
3. Start giving tasks — the agent uses the knowledge graph directly via MCP
```

The `sdd-orchestrator` profile has full access to the 8 MCP tools and knows the SDD workflow. You switch back to the default agent with Tab at any time.

**From the terminal:**

```bash
opencontext pack . --query "Implement rate limiting" --copy
# → paste the context pack into OpenCode chat for a one-shot task
```

**Full SDD workflow in OpenCode:**

```bash
opencontext harness run --workflow sdd --task "Add OAuth2 login"
# → creates run structure in .opencontext/runs/
# → switch to sdd-orchestrator in OpenCode, it picks up from there
```

---

### Claude Code

`opencontext install` installs into `~/.claude/`:

| File | Purpose |
|---|---|
| `CLAUDE.md` | Instructions — Claude reads this automatically on every session |
| `mcp.json` | Registers all 8 MCP tools |
| `settings.json` | Pre-approves the MCP tools (no manual allow needed) |

**Day-to-day workflow:**

```bash
# Start Claude Code in your project
claude

# Claude reads CLAUDE.md automatically.
# MCP tools are available — Claude uses them when relevant.
# You can also run CLI commands directly in the session:
opencontext pack . --query "Review the auth module" --copy
```

**Use MCP tools explicitly:**

```
> Use opencontext_context to find everything related to authentication
> Run opencontext_impact on UserModel before I change it
> Use opencontext_callers to trace who calls authenticate_user
```

**SDD with Claude Code:**

```bash
opencontext harness run --workflow sdd --task "Refactor payment flow"
# → Claude Code picks up the SDD structure from CLAUDE.md
# → use /sdd-new in the session to start a new change
```

---

### Cursor

`opencontext install` creates `.cursor/rules/opencontext.mdc` — Cursor loads this automatically for every conversation.

**Day-to-day workflow:**

```bash
# In Cursor's terminal panel:
opencontext pack . --query "How does the billing module work?" --copy
# → paste the context pack into Cursor chat (Cmd+L)
```

**With MCP (Cursor 0.43+):**

Once MCP is enabled in Cursor Settings → Features → MCP, the 8 tools are available directly:

```
# In chat:
> Use the OpenContext knowledge graph to find all callers of process_payment
> Check what would break if I rename UserAccount to Account
```

**Index on demand:**

```bash
opencontext index .   # re-index after major changes
opencontext knowledge-graph view --format tree   # visual project map
```

---

### Windsurf

`opencontext install` creates `~/.windsurf/rules/opencontext.md` — a Windsurf rules file that Cascade loads automatically.

**Day-to-day workflow:**

```bash
# In Windsurf's terminal:
opencontext pack . --query "Explain the data layer" --copy
# → paste into Cascade (Cmd+L)
```

For complex tasks, use the harness:

```bash
opencontext harness run --workflow sdd --task "Add caching to the API layer"
```

---

### Codex / Generic (any agent)

`opencontext install` creates an `AGENTS.md` at your project root. Any agent that reads instruction files picks this up automatically.

**Works everywhere — clipboard flow:**

```bash
opencontext pack . --query "your task here" --copy
# Paste into any chat: ChatGPT, Gemini, Claude.ai, Copilot Chat, etc.
```

```bash
# Or output to a file
opencontext pack . --query "Review the API layer" --output context.md
# Then attach or paste wherever you need it
```

---

### Any agent — MCP

If your agent supports the Model Context Protocol, start the MCP server and point your agent at it:

```bash
opencontext mcp   # Starts on stdio — works with any MCP-compatible agent
```

Available tools: `opencontext_search` · `opencontext_context` · `opencontext_callers` · `opencontext_callees` · `opencontext_impact` · `opencontext_node` · `opencontext_files` · `opencontext_status`

---

## How It Works

OpenContext sits between your codebase and your AI agent. It runs a 4-step pipeline on every request:

| Step | What happens | Command |
|---|---|---|
| **1. Index** | Builds a SQLite knowledge graph — symbols, call chains, imports, routes | `opencontext index .` |
| **2. Query** | Retrieves the top-K files ranked by semantic relevance to your task | `opencontext pack . --query "task"` |
| **3. Optimize** | Compresses, redacts secrets, enforces token budget | automatic |
| **4. Deliver** | Compact context pack → clipboard / file / API / MCP | `--copy` or `--output` |

No vector DB. No embeddings API. No cloud calls. Everything runs locally on SQLite + FTS5.

---

## Why OpenContext

**The core problem:** when an AI agent works on a task, it has no idea which files actually matter. The default is to send everything — or nothing useful. Either way, you pay in tokens, latency, and hallucinated context.

OpenContext solves this by building a **semantic knowledge graph** of your project — call chains, imports, framework routes, cross-language bridges — and using it to assemble a task-specific context pack: only what's relevant, secrets redacted, token budget enforced.

<table>
<tr>
<th>Without OpenContext</th>
<th>With OpenContext</th>
</tr>
<tr>
<td>

```
Your agent sees:
  src/auth.py        (maybe relevant)
  src/models.py      (maybe relevant)
  src/routes.py      (maybe relevant)
  tests/ (50 files)  (probably not)
  docs/ (20 files)   (probably not)
  ...161 more files  (almost certainly not)

~95,000 tokens per query
Secrets may be in plaintext
No call graph — deps guessed or missed
```

</td>
<td>

```
Your agent sees:
  src/auth.py        ✓ calls authenticate_user
  src/models.py      ✓ User model is a dependency
  ────────────────────────────────────────
  Everything else filtered out

~3,500 tokens per query  (up to 96% less)
Secrets redacted automatically
Call chain and impact traced precisely
```

</td>
</tr>
</table>

| | Send everything | Keyword grep | **OpenContext** |
|---|:---:|:---:|:---:|
| Token budget | ⚠️ Unbounded | ⚠️ Approximate | ✅ Enforced |
| Relevant symbols found | ❌ By chance | ⚠️ By name only | ✅ By call graph |
| Cross-file dependencies | ❌ Missed | ❌ Missed | ✅ Traced |
| Secrets in prompt | ⚠️ Possible | ⚠️ Possible | ✅ Auto-redacted |
| Token reduction | — | ~80% | **up to 96%** |
| Auditable trace | ❌ | ❌ | ✅ Full trail |
| Structured workflow | ❌ | ❌ | ✅ 8-phase SDD |

> Token reduction is measured by comparing the full project token count against a targeted context pack for the same query. Results vary by project size and query specificity — verified via the built-in benchmark suite (`opencontext benchmark run`).

---

## Feature Overview

### Knowledge Graph

Indexes your project into a queryable SQLite graph. Understands call chains, imports, and framework routes — no external services required.

```bash
opencontext index .

opencontext knowledge-graph search "authenticate"          # Find symbols
opencontext knowledge-graph callers "authenticate_user"    # Who calls this
opencontext knowledge-graph impact "UserModel" --radius 2  # What breaks if I change this
opencontext knowledge-graph view --format tree             # Visual project structure
```

**Framework routing** — detects URL-to-handler mappings for Django, FastAPI, Flask, Express, and NestJS:

```bash
opencontext routes scan . --framework fastapi
```

**Cross-language bridges** — HTTP calls, gRPC stubs, subprocesses, IPC across `.py`, `.ts`, `.go`, `.rs`, and more:

```bash
opencontext bridges scan . --type GRPC --json
```

---

### Spec-Driven Development (SDD)

An 8-phase governance harness that keeps AI agents disciplined through every change:

```
explore → propose → spec → design → tasks → apply → verify → archive
```

The harness enforces token budgets, quality gates, and artifact persistence at each phase. Your AI agent executes the work; the harness ensures nothing ships without passing `verify`.

```bash
opencontext harness run --workflow sdd --task "Add OAuth2 login"
opencontext harness list

opencontext sync issues --change my-feature --dry-run   # Preview GitHub Issues sync
opencontext sync issues --change my-feature
```

**SDD enforces:** per-phase token budgets · structured artifacts · test runs at verify · full archive trail

---

### Safety — Secure by Default

| Surface | Default | Override |
|---|---|---|
| External providers | ❌ Disabled | Enable per-provider in config |
| MCP tools | ❌ Disabled | Allowlist required |
| Network egress | ❌ Denied | `providers.external_enabled: true` |
| Secrets in prompts | ✅ Redacted | Not configurable |
| Raw traces | ❌ Off | `traces.store_raw_context: true` |
| Missing policy | ✅ Fail closed | `fail_closed: false` |

```bash
opencontext preset apply privacy   # Maximum privacy mode
opencontext doctor security        # Security audit
```

---

### Workflow Presets

```bash
opencontext preset apply fast        # Cheap model, 2K token budget
opencontext preset apply deep        # Premium model, 8K budget
opencontext preset apply privacy     # Air-gapped, fail-closed
opencontext preset apply strict-tdd  # Enforce test-first discipline
```

| Preset | Token budget | Use case |
|---|---|---|
| `fast` | 2K / 600 | Quick iteration |
| `deep` | 8K / 2K | Architecture work |
| `privacy` | default | Sensitive codebases |
| `strict-tdd` | default | High-stakes changes |
| `air-gapped` | default | Enterprise / offline |

---

### Multi-perspective Review

Four independent reviewers — **architect**, **security**, **performance**, **ux** — each with a distinct role prompt, findings merged by severity:

```bash
opencontext review --party --context "$(git diff HEAD~1)"
opencontext review --party --roles "architect,security" --output review.md
```

> Requires a configured LLM provider. Without one, each reviewer returns a graceful "provider not configured" message. Run `opencontext config wizard` to set one up.

---

## Benchmark

Reproducible. Run it yourself:

```bash
python -m pytest tests/core/test_comparative_benchmark.py -v -s
```

| Task | Difficulty | Naive tokens | OpenContext | Reduction |
|---|---|---:|---:|---:|
| Add method to BridgeDetector | Simple | 38,381 | 2,482 | **93.5%** |
| Add --json flag to CLI command | Medium | 38,188 | 2,145 | **94.4%** |
| Wire tracing to WorkflowEngine | Hard | 24,636 | 6,509 | **73.6%** |
| **Average** | | | | **87.4%** |

All 3 tasks: SDD ✓ · TDD ✓ · Secrets clean ✓

*Methodology: naive baseline = all files in the relevant directory. Token estimate: `len(text) / 4`. Reproducible — run `opencontext benchmark run` or `python -m pytest tests/core/test_comparative_benchmark.py -v -s`.*

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

## CLI Reference

```bash
# Setup
opencontext install           # Auto-detect & configure
opencontext install --yes     # Non-interactive (CI-friendly)
opencontext doctor            # Health check
opencontext update && opencontext upgrade

# Context
opencontext index .
opencontext pack . --query "task" --copy
opencontext pack . --query "task" --format json

# Knowledge Graph
opencontext knowledge-graph search "symbol"
opencontext knowledge-graph callers "func_name"
opencontext knowledge-graph impact "ClassName" --radius 2
opencontext knowledge-graph view --format tree

# SDD / Workflow
opencontext harness run --workflow sdd --task "description"
opencontext harness list
opencontext workflow resume <run-id>
opencontext sync issues --change <name>

# Analysis
opencontext routes scan . --framework fastapi
opencontext bridges scan . --type HTTP --json
opencontext review --party --context "$(git diff HEAD~1)"

# Config
opencontext config wizard
opencontext preset list && opencontext preset apply <name>

# Memory
opencontext memory search "query"
opencontext memory harvest
opencontext memory gc

# Plugins & Extensions
opencontext plugin search && opencontext plugin install <name>
opencontext extension search && opencontext extension install <name>

# Telemetry
opencontext telemetry show
opencontext benchmark run
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

## Install

| Method | Command |
|---|---|
| pip | `pip install opencontext-cli` |
| One-liner (Linux/macOS) | `curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh \| bash` |
| One-liner (Windows) | `irm https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.ps1 \| iex` |
| Source | `git clone … && pip install -e packages/*` |

Requires **Python 3.12+**. No API keys required for core functionality.

```bash
pytest                          # Tests (800+)
ruff check .                    # Lint
mypy packages/opencontext_core  # Types
```

---

MIT · [LICENSE](LICENSE) · [SECURITY.md](SECURITY.md) · [CONTRIBUTING.md](CONTRIBUTING.md)
