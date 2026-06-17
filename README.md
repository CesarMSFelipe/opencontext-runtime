<p align="center">
  <img src="docs/assets/logo.svg" alt="OpenContext" width="120" height="120">
</p>

<h2 align="center">OpenContext Runtime</h2>

<p align="center">
  <b>Your AI agent reads the whole repo to change two files.<br>
  OpenContext gives it the handful that matter — verified, offline, in milliseconds.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/up_to_96%25_token_reduction-benchmarked-00C9A7?style=flat-square" alt="Up to 96% token reduction">
  <img src="https://img.shields.io/badge/offline--first-no_API_key-00A8E8?style=flat-square&logo=python&logoColor=white" alt="Works offline">
  <img src="https://img.shields.io/badge/1500%2B_tests-passing-00C9A7?style=flat-square" alt="1500+ tests passing">
  <img src="https://img.shields.io/badge/13_MCP_tools-Claude_%7C_Cursor_%7C_Copilot-845EC2?style=flat-square" alt="13 MCP tools">
  <img src="https://img.shields.io/badge/license-MIT-gray?style=flat-square" alt="MIT">
</p>

<p align="center">
  <a href="#-quick-start"><b>Quick Start</b></a> ·
  <a href="#-how-it-works">How It Works</a> ·
  <a href="#-agentic-loop">Agentic Loop</a> ·
  <a href="#-knowledge-graph">Knowledge Graph</a> ·
  <a href="#-mcp-tools">MCP Tools</a> ·
  <a href="#-memory">Memory</a> ·
  <a href="#-benchmark">Benchmark</a> ·
  <a href="#-install">Install</a>
</p>

---

## ⚡ Quick Start

```bash
pip install opencontext-cli

cd your-project

# See the difference in 30 seconds — no setup, no API key
opencontext demo

# Set up your project (auto-detects stack, builds graph, wires your agent)
opencontext install

# Get a verified, minimal context pack
opencontext pack . --query "How does authentication work?" --copy
```

`opencontext demo` runs on your actual repo and shows you exactly what it filters out and why. Run it before anything else.

---

## 🧠 How It Works

Every agent query runs through a deterministic pipeline — no LLM guessing what's relevant:

```
query → classify risk → build ContextContract → retrieve from graph
      → score (centrality + call distance + git + memory)
      → pack minimum sufficient context → validate 16 gates → deliver
```

**Before vs After:**

<table>
<tr>
<th>Without OpenContext</th>
<th>With OpenContext</th>
</tr>
<tr>
<td>

```
Agent reads everything:
  src/auth.py        (maybe relevant)
  src/models.py      (maybe relevant)
  tests/ (50 files)  (probably not)
  ...

Tens of thousands of tokens
Secrets may be in plaintext
No call graph — deps guessed
No memory of past failures
```

</td>
<td>

```
Agent reads exactly what it needs:
  src/auth/middleware.py  ✓ verified
  src/auth/token.py       ✓ verified
  tests/test_auth.py      ✓ risk tier
  ──────────────────────────────────
  Everything else filtered out

Up to 96% fewer tokens
Secrets auto-redacted
Call chain traced precisely
Past failures boost right symbols
```

</td>
</tr>
</table>

Every context pack is backed by a **ContextContract** — a structured plan stating what's required, what must be verified, and why each file was included:

```bash
$ opencontext contract build --query "fix crash in auth middleware"
```

```yaml
task: fix crash in auth middleware
task_type: bugfix
risk_tier: precise
token_budget: 16000
required_symbols: ['*crash*', '*auth*', '*middleware*']
must_verify: [run-tests, lint, type-check]
```

| Risk tier | Token budget | When |
|-----------|-------------|------|
| `cheap` | 8,000 | Renames, docs, trivial fixes |
| `precise` | 16,000 | Bugfixes, features, refactors |
| `critical` | 28,000 | Security, migrations, architecture |

---

## 🤖 Agentic Loop

The loop is how you hand a real task to OpenContext end-to-end. Interactive checkpoints, retries on failure, compressed output.

```bash
# Full 8-phase SDD workflow
opencontext loop --task "add OAuth2 login" --flow full

# Quick: explore → apply → verify
opencontext loop --task "rename variable in utils" --flow quick

# No prompts — gates decide
opencontext loop --task "fix payment bug" --flow autonomous

# Retry up to 3× if verify fails
opencontext loop --task "..." --flow full --max-rounds 3

# Preview without running
opencontext loop --task "..." --flow full --dry-run
```

**Flow tracks:**

| Track | Phases | For |
|-------|--------|-----|
| `quick` | explore → apply → verify | Simple fixes |
| `standard` | explore → spec+design → apply → verify | Features, refactors |
| `full` | All 8 phases | Architecture, security |
| `autonomous` | All 8, no prompts | CI/CD, automation |

**Built-in agents** (all run locally, no LLM required):

| Agent | What it does |
|-------|-------------|
| `context-planner` | Builds ContextContract from the knowledge graph |
| `tdd-enforcer` | Red→green→refactor cycle validation |
| `security-audit` | Secret leakage scan |
| `code-review` | Graph analysis + structured review prompt |

---

## 🕸️ Knowledge Graph

SQLite-backed, offline, no external services. Indexes symbols, call chains, imports, and framework routes across your entire codebase.

```bash
opencontext index .

# Search and traverse
opencontext knowledge-graph search "authenticate"
opencontext knowledge-graph callers "authenticate_user"     # who calls this
opencontext knowledge-graph impact "UserModel" --radius 2  # blast radius

# Audit: why did these files make it into the context?
opencontext explain "fix crash in auth middleware"
```

**Framework routes** — URL-to-handler mappings (Django, FastAPI, Flask, Express, NestJS):

```bash
opencontext routes scan . --framework fastapi
```

**Cross-language bridges** — HTTP, gRPC, subprocess calls across `.py` / `.ts` / `.go` / `.rs`:

```bash
opencontext bridges scan . --type HTTP --json
```

---

## 🔌 MCP Tools

13 tools pre-approved after `opencontext install` — every read goes through the verified pipeline, every edit targets exact symbol boundaries:

```
# Read (9)
opencontext_search       opencontext_context      opencontext_callers
opencontext_callees      opencontext_impact       opencontext_node
opencontext_files        opencontext_status       opencontext_trace

# Symbol-level edits (4)
opencontext_replace_symbol_body    opencontext_insert_before_symbol
opencontext_insert_after_symbol    opencontext_rename_symbol
```

Works out of the box with Claude Code, Cursor, Copilot, Windsurf, OpenCode, and any MCP-compatible editor.

```bash
# Wire your agent manually
opencontext setup claude-code
opencontext setup cursor
opencontext setup --all
```

---

## 🧠 Memory

Five local layers — SQLite + FTS5, zero external services:

| Layer | Stores |
|-------|--------|
| `SEMANTIC` | Stable project facts |
| `EPISODIC` | Past task outcomes |
| `PROCEDURAL` | Learned rules: "for KnowledgeGraph changes, always check graph_db.py" |
| `WORKING` | Current task context |
| `FAILURE` | Which symbols caused test failures |

Memory feeds back into retrieval scoring — files linked to past failures rank higher automatically.

```bash
opencontext memory search "auth middleware"
opencontext memory collect          # extract learnings from last run
opencontext memory review           # confirm or correct high-stakes memories
opencontext memory gc --dry-run     # preview what would be pruned
```

---

## 🔒 Security

Nothing leaves your machine by default.

| Surface | Default |
|---------|---------|
| External providers | ❌ Disabled |
| Secrets in context | ✅ Auto-redacted |
| MCP tools | ❌ Blocked until allow-listed |
| Fail on missing policy | ✅ Fail closed |

```bash
opencontext security scan .      # scan for secret leakage patterns
opencontext doctor security      # full security diagnostics
opencontext preset apply privacy # air-gapped, fail-closed, no egress
```

---

## 📊 Benchmark

Reproducible — run it on your own repo:

```bash
opencontext demo           # 30 seconds, no setup
opencontext benchmark run  # full structured benchmark
```

Results on OpenContext's own codebase:

| Task | Naive | OpenContext | Reduction |
|------|------:|------------:|----------:|
| Add `count_by_type()` to BridgeDetector | 49,394 | 2,474 | **95.0%** |
| Add `--json` flag to `bridges scan` | 59,363 | 2,273 | **96.2%** |
| Add RuntimeTrace to WorkflowEngine | 27,556 | 6,905 | **74.9%** |
| **Average** | | | **88.7%** |

---

## 🔧 Configuration

```bash
opencontext config wizard          # interactive setup
opencontext preset apply strict-tdd
opencontext preset apply fast      # budget model, low latency
opencontext preset apply deep      # premium model, max quality
opencontext preset apply privacy   # air-gapped, fail-closed
opencontext preset list
```

Key config in `opencontext.yaml`:

```yaml
models:
  default:
    provider: mock   # swap: anthropic / openai / openrouter / local

memory:
  enabled: true
  harvest_after_run: true

security:
  mode: private_project
  fail_closed: true
```

---

## 📖 Documentation

| Topic | |
|-------|--|
| Getting Started | [Quickstart](docs/getting-started/quickstart.md) · [Installation](docs/getting-started/installation.md) · [Troubleshooting](docs/getting-started/troubleshooting.md) |
| Architecture | [Overview](docs/architecture/overview.md) · [Context Pack Builder](docs/architecture/context-pack-builder.md) · [Safety Layer](docs/architecture/safety-layer.md) |
| Agentic Loop | [Flow Modes](docs/workflows/modes.md) · [Custom Workflows](docs/workflows/custom-workflows.md) |
| SDD Workflow | [SDD Guide](docs/workflows/sdd-workflow.md) |
| Memory | [Overview](docs/memory/overview.md) · [Session Harvesting](docs/memory/session-harvesting.md) |
| Token Efficiency | [Compression](docs/token-efficiency/compression.md) · [Benchmarks](docs/token-efficiency/overview.md) |
| Security | [Threat Model](docs/security/threat-model.md) · [Data Classification](docs/security/data-classification.md) |
| Integrations | [Python SDK](docs/integrations/python-sdk.md) · [API](docs/integrations/api.md) · [GitHub Action](docs/integrations/github-action.md) |
| Enterprise | [Air-Gapped](docs/enterprise/air-gapped.md) · [Governance](docs/enterprise/governance-reports.md) |

---

## 🚀 Install

| Method | Command |
|--------|---------|
| pip | `pip install opencontext-cli` |
| pipx (isolated) | `pipx install opencontext-cli` |
| uv | `uv tool install opencontext-cli` |
| Linux / macOS | `curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh \| bash` |
| Windows | `irm https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.ps1 \| iex` |
| Portable binary | `make binary` → `dist/opencontext.pyz` (runs anywhere Python 3.12+ is present) |

Requires **Python 3.12+**. No API key required for core functionality.

```bash
# Verify after install
opencontext verify
opencontext doctor
```

---

## CLI at a Glance

```bash
# Setup
opencontext install              # auto-detect, build graph, wire agent
opencontext demo                 # 30-second proof on your own repo
opencontext verify               # health check
opencontext doctor               # deep diagnostics

# Context
opencontext index .
opencontext pack . --query "task" --copy
opencontext explain "task"       # why each file is (or isn't) included
opencontext verified-context "task"
opencontext contract build --query "task"

# Agentic loop
opencontext loop --task "..." --flow full
opencontext loop --task "..." --flow quick
opencontext loop --task "..." --dry-run

# Knowledge graph
opencontext knowledge-graph search "symbol"
opencontext knowledge-graph callers "func"
opencontext knowledge-graph impact "Class" --radius 2

# Memory
opencontext memory search "query"
opencontext memory collect
opencontext memory gc --dry-run

# Analysis
opencontext routes scan . --framework fastapi
opencontext bridges scan . --type HTTP --json
opencontext security scan .
opencontext benchmark run

# Updates
opencontext update && opencontext upgrade
opencontext plugin search
opencontext plugin install <name>
```

---

MIT · [LICENSE](LICENSE) · [SECURITY.md](SECURITY.md) · [CONTRIBUTING.md](CONTRIBUTING.md)
