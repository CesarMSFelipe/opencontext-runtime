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
  <a href="#-aicx-bytecode">AICX Bytecode</a> ·
  <a href="#-agentic-loop--harness">Loop & Harness</a> ·
  <a href="#-knowledge-graph">Knowledge Graph</a> ·
  <a href="#-mcp-tools">MCP Tools</a> ·
  <a href="#-memory">Memory</a> ·
  <a href="#-benchmark">Benchmark</a> ·
  <a href="#-install">Install</a>
</p>

---

## ⚡ Quick Start

**Start here — no setup, no API key needed:**

```bash
pip install opencontext-cli
cd your-project
opencontext demo
```

`demo` runs on your actual repo and shows you the token reduction in real numbers. See the value before you commit to anything.

**Then set up:**

```bash
opencontext install   # detects your stack, builds the graph, wires your editor
```

The install wizard asks which editor you use and guides you to the first real result — a verified context query in your editor.

---

## 🧠 How It Works

Every agent query runs through a deterministic pipeline — no LLM guessing what's relevant:

```
query → classify risk → build ContextContract → retrieve from graph
      → score (centrality + call distance + git + memory)
      → pack minimum sufficient context → validate gates → deliver
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

Every context pack is backed by a **ContextContract** — a structured plan with risk tier, token budget, required symbols, and verification gates:

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

## 🔬 AICX Bytecode

Context packs are serialized as **AICX bytecode** — a compact, verifiable wire format with a cryptographic checksum. Agents can validate context integrity before acting on it.

```bash
$ opencontext bytecode compile --query "fix auth bug"
```

```
AICX/1
REQ id:8d566cc2 surface:cli risk:normal budget:16000 q:q001
EVID id:graph:ex src:s002 type:graph_symbol conf:1.00 fresh:unknown tok:99  mode:handle
EVID id:graph:pa src:s003 type:graph_symbol conf:1.00 fresh:unknown tok:737 mode:handle
EVID id:graph:ex src:s004 type:graph_symbol conf:1.00 fresh:unknown tok:180 mode:handle
EVID id:file:tes src:s007 type:file         conf:0.67 fresh:current tok:346 mode:handle
EVID id:file:tes src:s008 type:file         conf:0.67 fresh:current tok:612 mode:handle
GATE provenance
GATE freshness
GATE coverage
TRUST status:sufficient why:t012
CHK 50f4ba168b59

instructions     : 15
evidence items   : 10
dictionary keys  : 12
original tokens  : 5,607
bytecode tokens  : 250
token reduction  : 95.5%
checksum         : ✓ valid
```

Each `EVID` line carries **confidence**, **freshness**, and **token cost**. The `GATE` lines record which quality checks passed. `CHK` is the tamper-evident checksum. Decode back to a human-readable evidence plan at any time:

```bash
opencontext bytecode inspect   # latest compiled pack
opencontext bytecode decode <path.aicx>
```

---

## 🤖 Agentic Loop & Harness

### Loop — high-level interface

Hand a task description to OpenContext. It plans the phases, gates each transition, and retries on failure.

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

| Track | Phases | For |
|-------|--------|-----|
| `quick` | explore → apply → verify | Simple fixes |
| `standard` | explore → spec+design → apply → verify | Features, refactors |
| `full` | All 8 phases | Architecture, security |
| `autonomous` | All 8, no prompts | CI/CD, automation |

### Harness — low-level engine

The harness is what the loop runs under the hood. Each phase has an explicit token budget and a set of gates that must pass before the next phase starts.

```bash
$ opencontext harness run --workflow sdd --task "add rate limiting to API"
```

```
Harness Run: sdd-c9135ab0112f
  Workflow: sdd
  Task: add rate limiting to API
  Status: passed
  Phases: 9
    explore : 2685/3000 tokens — passed
    propose : ─────────────────  passed
    spec    : ─────────────────  passed
    design  : ─────────────────  passed
    tasks   : ─────────────────  passed
    apply   : ─────────────────  passed
    verify  : ─────────────────  passed
    review  : ─────────────────  passed
    archive : ─────────────────  passed
  Gates: 22
```

Each run persists its full artifact trail to `.opencontext/runs/<run_id>/` — proposal, decisions, ledger, gates, verify report.

```bash
opencontext harness list              # available workflows
opencontext harness report <run_id>   # inspect past run
```

### Built-in agents

| Agent | Role |
|-------|------|
| `context-planner` | Builds ContextContract from the knowledge graph |
| `tdd-enforcer` | Red→green→refactor cycle validation |
| `security-audit` | Secret leakage scan |
| `code-review` | Graph analysis + structured review prompt |
| `mutation-analyst` | Blast-radius analysis before apply |

---

## 🕸️ Knowledge Graph

SQLite-backed, offline, no external services. Indexes symbols, call chains, imports, and framework routes across your entire codebase. Hybrid retrieval: BM25 (FTS5) + manifests fused via RRF.

```bash
opencontext index .

opencontext knowledge-graph search "authenticate"
opencontext knowledge-graph callers "authenticate_user"     # who calls this?
opencontext knowledge-graph impact "UserModel" --radius 2   # blast radius

opencontext explain "fix crash in auth middleware"           # why each file included
```

**Framework routes** — URL-to-handler mappings out of the box:

```bash
opencontext routes scan . --framework fastapi   # Django, FastAPI, Flask, Express, NestJS
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
opencontext setup claude-code
opencontext setup cursor
opencontext setup --all
```

---

## 🧠 Memory

Five local layers — SQLite + FTS5, zero external services. Memory feeds back into retrieval scoring: files linked to past failures rank higher automatically.

| Layer | Stores |
|-------|--------|
| `SEMANTIC` | Stable project facts |
| `EPISODIC` | Past task outcomes |
| `PROCEDURAL` | Learned rules: "for KnowledgeGraph changes, always check graph_db.py" |
| `WORKING` | Current task context |
| `FAILURE` | Which symbols caused test failures |

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
opencontext security scan .       # scan for secret leakage patterns
opencontext doctor security       # full security diagnostics
opencontext preset apply privacy  # air-gapped, fail-closed, no egress
```

---

## 📊 Benchmark

Reproducible — run it on your own repo:

```bash
opencontext demo           # 30 seconds, no setup
opencontext benchmark run  # full structured benchmark
```

`opencontext benchmark run` scores 7 scenarios across 5 dimensions (completeness, relevance, token efficiency, safety, freshness). Results on this repo:

| Scenario | Score | Token efficiency |
|----------|------:|-----------------:|
| completeness/minimal | 95.0 | 80% |
| completeness/multi_file | 87.5 | 50% |
| relevance/focused | 98.0 | 92% |
| efficiency/large_project | 99.0 | 96% |
| safety/clean_context | 95.0 | 80% |
| freshness/recent | 87.5 | 50% |
| freshness/stale | 81.5 | 50% |
| **Average** | **91.9** | |

The `efficiency/large_project` scenario consistently shows 96%+ token reduction on large codebases. Exact numbers vary by project size and query specificity — run `opencontext demo` on your own repo to see real figures.

---

## 🔧 Configuration

```bash
opencontext config wizard

opencontext preset apply strict-tdd
opencontext preset apply fast      # budget model, low latency
opencontext preset apply deep      # premium model, max quality
opencontext preset apply privacy   # air-gapped, fail-closed
opencontext preset list
```

```yaml
# opencontext.yaml
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
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) · [Architecture deep-dive](docs/architecture/overview.md) |

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
opencontext verify   # health check
opencontext doctor   # deep diagnostics
```

---

## CLI at a Glance

```bash
# Setup & health
opencontext install              # auto-detect, build graph, wire agent
opencontext demo                 # 30-second proof on your own repo
opencontext verify               # health check
opencontext doctor               # deep diagnostics

# Context
opencontext index .
opencontext pack . --query "task" --copy
opencontext explain "task"
opencontext verified-context "task"
opencontext contract build --query "task"

# AICX bytecode
opencontext bytecode compile --query "task"
opencontext bytecode inspect
opencontext bytecode decode <path.aicx>

# Agentic loop & harness
opencontext loop --task "..." --flow full
opencontext loop --task "..." --flow quick --dry-run
opencontext harness run --workflow sdd --task "..."
opencontext harness list
opencontext harness report <run_id>

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

# Config & plugins
opencontext config wizard
opencontext preset apply <name>
opencontext plugin search
opencontext plugin install <name>
opencontext update && opencontext upgrade
```

---

MIT · [LICENSE](LICENSE) · [SECURITY.md](SECURITY.md) · [CONTRIBUTING.md](CONTRIBUTING.md)
