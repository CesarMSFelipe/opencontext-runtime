<p align="center">
  <img src="docs/assets/logo.svg" alt="OpenContext" width="120" height="120">
</p>

<h2 align="center">OpenContext Runtime</h2>

<p align="center">
  <b>The verified context runtime for AI agents.</b><br>
  <sub>Plans · Verifies · Remembers · Learns · Ships minimum sufficient context</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/up_to_96%25_token_reduction-benchmarked-00C9A7?style=flat-square" alt="Up to 96% token reduction">
  <img src="https://img.shields.io/badge/offline--first-no_API_key-00A8E8?style=flat-square&logo=python&logoColor=white" alt="Works offline">
  <img src="https://img.shields.io/badge/1500%2B_tests-passing-00C9A7?style=flat-square" alt="1500+ tests passing">
  <img src="https://img.shields.io/badge/14%2B_agents-Claude_%7C_Cursor_%7C_Copilot-845EC2?style=flat-square" alt="14+ agents">
  <img src="https://img.shields.io/badge/license-MIT-gray?style=flat-square" alt="MIT">
</p>

<p align="center">
  <a href="#-quick-start"><b>Quick Start</b></a> &nbsp;·&nbsp;
  <a href="#-how-it-works">How It Works</a> &nbsp;·&nbsp;
  <a href="#-agentic-loop">Agentic Loop</a> &nbsp;·&nbsp;
  <a href="#-sdd--tdd">SDD + TDD</a> &nbsp;·&nbsp;
  <a href="#-knowledge-graph">Knowledge Graph</a> &nbsp;·&nbsp;
  <a href="#-memory">Memory</a> &nbsp;·&nbsp;
  <a href="#-compression">Compression</a> &nbsp;·&nbsp;
  <a href="#-benchmark">Benchmark</a> &nbsp;·&nbsp;
  <a href="#-cli-reference">CLI</a>
</p>

---

```sh
$ opencontext loop --task "fix crash in auth middleware" --flow full --dry-run

------------------------------------------------------------
  OpenContext Loop  [full]  compress:efficient
  Task: fix crash in auth middleware
------------------------------------------------------------

Dry run — phases that would execute:
  - EXPLORE
  - PROPOSE
  - SPEC
  - DESIGN
  - TASKS
  - APPLY
  - VERIFY
  - ARCHIVE
```

---

## ⚡ Quick Start

```bash
# Install
pip install opencontext-cli

# Set up your project (auto-detects stack, builds graph, configures agent)
cd your-project
opencontext install

# Run your first verified context pack
opencontext pack . --query "How does authentication work?" --copy

# Or launch the full agentic loop
opencontext loop --task "fix crash in auth middleware" --flow full
```

`opencontext install` does five things automatically:

1. **Detects your stack** — Python, Node, Go, Rust, Terraform, and more
2. **Builds the knowledge graph** — symbols, call chains, imports, framework routes
3. **Configures your agent** — generates the right instruction file for your editor
4. **Sets up MCP tools** — pre-approves 13 tools (9 read + 4 symbol-level edits), all routed through the verified pipeline
5. **Verifies the setup** — health check before finishing

> **No API keys. No external services.** Everything runs offline on your machine.

---

## 🧠 How It Works

OpenContext is not a RAG wrapper. It's a runtime that **plans, verifies, remembers, and learns** what minimum sufficient context each task needs.

### Before vs After

<table>
<tr>
<th>Without OpenContext</th>
<th>With OpenContext</th>
</tr>
<tr>
<td>

```
Agent sees every file in scope:
  src/auth.py        (maybe relevant)
  src/models.py      (maybe relevant)
  tests/ (50 files)  (probably not)
  ...and more

Tens of thousands of tokens per query
Secrets may be in plaintext
No call graph — deps guessed or missed
No memory of past failures
No verification before shipping
```

</td>
<td>

```
Agent sees only what the task needs:
  src/auth/middleware.py   ✓ verified required
  src/auth/token.py        ✓ verified required
  tests/test_auth.py       ✓ required by risk tier
  ─────────────────────────────────────────────
  Everything else filtered out

Up to 96% fewer tokens (benchmarked)
Secrets auto-redacted
Call chain traced precisely
Past failures boost relevant symbols
16 quality gates validated before delivery
```

</td>
</tr>
</table>

### The Pipeline

Every task runs through a verified pipeline:

```
receive task
  → classify task type + risk (deterministic, no LLM)
  → build ContextContract (known / unknown / must verify)
  → plan context (budget: 8k / 16k / 28k tokens by risk tier)
  → retrieve from knowledge graph
  → score with multiple signals (graph centrality, call distance, risk...)
  → pack minimum sufficient context
  → compress (terse / compact / efficient / none by risk tier)
  → validate 16 quality gates
  → deliver verified context to agent
  → harvest learnings into memory
```

The agent receives a **ContextContract** — not "these files might be relevant":

```bash
$ opencontext contract build --query "fix crash in auth middleware"
```

```yaml
task: fix crash in auth middleware
task_type: bugfix
risk_tier: precise
token_budget: 16000

required_symbols:
  - '*crash*'
  - '*auth*'
  - '*middleware*'

must_verify:
  - id: run-tests
  - id: lint
  - id: type-check
```

Risk tiers and budgets:

| Risk tier | Token budget | Used when |
|-----------|-------------|-----------|
| `cheap` | 8,000 | Renames, docs, config, trivial fixes |
| `precise` | 16,000 | Bugfixes, features, refactors |
| `critical` | 28,000 | Security, migrations, architecture |

---

## 🤖 Agentic Loop

The loop is the primary way to use OpenContext for real tasks. Interactive checkpoints, multi-agent execution, compressed output.

```bash
# Full 8-phase SDD workflow with user checkpoints
opencontext loop --task "add OAuth2 login" --flow full

# Faster: skip spec/design, straight to apply
opencontext loop --task "rename variable in utils" --flow quick

# No checkpoints — gates decide whether to continue
opencontext loop --task "fix payment bug" --flow autonomous

# Retry up to 3 times if verification fails
opencontext loop --task "..." --flow full --max-rounds 3

# Preview without executing
opencontext loop --task "..." --flow full --dry-run

# Control compression of agent output
opencontext loop --task "..." --compress efficient   # maximum reduction
opencontext loop --task "..." --compress terse       # prose only
opencontext loop --task "..." --compress none        # raw output
```

### Flow Tracks

| Track | Phases | Use for |
|-------|--------|---------|
| `quick` | explore → apply → verify | Simple fixes, renames |
| `standard` | explore → spec+design → apply → verify | Features, refactors |
| `full` | All 8 phases | Architecture, security, migrations |
| `autonomous` | All 8 phases, no prompts | CI/CD, scripts, automation |

### Built-in Agents

The loop orchestrates five specialized agents, each running in the right mode:

| Agent | Mode | What it does |
|-------|------|-------------|
| `context-planner` | Local | Builds ContextContract using the knowledge graph |
| `tdd-enforcer` | Local | Runs test suite, reports red/green cycle status |
| `mutation-analyst` | Local | Measures test quality via mutation analysis (requires mutation framework) |
| `security-audit` | Local | Scans for secret leakage patterns in files |
| `code-review` | Hybrid | Graph analysis locally + review prompt for host LLM |

Local agents need no LLM. Hybrid agents generate structured prompts your current agent executes — no double billing, no API key required.

### Using Agents via SDK

```python
import asyncio
from pathlib import Path
from opencontext_core.agents import AGENT_REGISTRY
from opencontext_core.agents.base import AgentConfig

config = AgentConfig(
    name="security-audit",
    type="security-audit",
    objectives=["scan for leaked credentials"],
    scope={"paths": ["src/"]},
)
agent = AGENT_REGISTRY["security-audit"](config, Path("."))
result = asyncio.run(agent.execute())
print(result["finding_count"], "findings,", "clean:", result["clean"])
```

---

## 📐 SDD + TDD

OpenContext enforces **Spec-Driven Development** as the default workflow for non-trivial changes. Eight phases. Zero guesswork. Full traceability.

```
explore → propose → spec → design → tasks → apply → verify → archive
```

Each phase:
- Runs inside the harness with a token budget
- Produces auditable YAML/JSON artifacts
- Passes through quality gates before proceeding
- Records its trace in the memory graph

```bash
# Run full SDD workflow
opencontext harness run --workflow sdd --task "Add rate limiting to API"

# Same workflow, interactive
opencontext loop --task "Add rate limiting to API" --flow full
```

### TDD Integration

The `tdd-enforcer` agent validates the red→green→refactor cycle at every verify phase. With `strict-tdd` preset, the harness **blocks** apply if no failing test was written first:

```bash
opencontext preset apply strict-tdd
opencontext loop --task "add feature X" --flow full
# → VERIFY blocks if no failing test exists before APPLY
```

### Mutation Testing

Measures test quality beyond line coverage — kills mutants to prove tests actually catch regressions. Requires a compatible mutation testing framework to be installed.

```bash
opencontext mutation run --scope changed --threshold 80
```

Without a mutation framework:
```
Warning: Mutation analysis framework not found in this environment.
```

Configure in `opencontext.yaml`:

```yaml
testing:
  mutation:
    enabled: true
    threshold: 80
    fail_on_low_score: false   # true = block archive below threshold
```

### Quality Gates

Every verify phase runs 16 gates automatically:

| Gate | Checks |
|------|--------|
| `project-index-exists` | Knowledge graph is indexed |
| `context-pack-created` | Context was built and delivered |
| `token-budget` | Pack within tier budget |
| `trace-id-created` | Trace ID recorded for audit |
| `security-scan` | No secret patterns found |
| `artifact-persisted` | Artifacts saved to run directory |
| `confidence` | Evidence confidence meets threshold |
| `privacy` | Privacy policy satisfied |
| `no-secret-leakage` | Context pack is clean |
| `included-sources-present` | Required symbols present in pack |
| `omissions-recorded` | Omissions documented in trace |
| `provider-policy-passed` | Provider rules satisfied |
| `approval-required-for-writes` | Writes confirmed by user/policy |
| `no-high-risk-exports` | No confidential data to external providers |
| `review-artifact-created` | Review trail persisted |
| `failing-test-exists` | TDD: failing test before apply — advisory by default, blocks in strict-tdd |

---

## 🕸️ Knowledge Graph

Indexes your project into a queryable SQLite graph. Understands call chains, imports, framework routes, and cross-language boundaries. No external services.

```bash
opencontext index .

opencontext knowledge-graph search "authenticate"
opencontext knowledge-graph callers "authenticate_user"      # who calls this
opencontext knowledge-graph impact "UserModel" --radius 2    # what breaks if changed
opencontext knowledge-graph view --format tree
```

**Framework routes** — URL-to-handler mappings for Django, FastAPI, Flask, Express, NestJS:

```bash
opencontext routes scan . --framework fastapi
```

**Cross-language bridges** — HTTP calls, gRPC stubs, subprocesses across `.py`, `.ts`, `.go`, `.rs`:

```bash
opencontext bridges scan . --type GRPC --json
```

---

## 🧠 Memory

Five memory layers — all local, all offline, all SQLite+FTS5:

| Layer | What it stores |
|-------|---------------|
| `SEMANTIC` | Stable project facts: "repo separates core from CLI" |
| `EPISODIC` | Past experiences: "task X failed because graph_db.py was missing" |
| `PROCEDURAL` | Learned rules: "for KnowledgeGraph changes, always read graph_db.py" |
| `WORKING` | Current task context (cleared after archive) |
| `FAILURE` | Failure patterns: which symbols and files caused test failures |

Memory enriches every context pack. Symbols linked to past failures are boosted in retrieval scoring. Procedural rules are injected into the ContextContract automatically.

```bash
opencontext memory search --query "auth middleware failures"
opencontext memory harvest           # extract learnings from latest run
opencontext memory gc --dry-run      # preview decay candidates
```

After each run, the harvester automatically:
- Records the episodic trace
- Extracts procedural rules from failures
- Links failure patterns to symbols in the graph
- Applies confidence decay to stale records by half-life

---

## 🗜️ Compression

Four strategies, applied automatically by risk tier — zero configuration needed:

| Strategy | Tier | What it does |
|----------|------|-------------|
| `none` | Critical | Never compress — full fidelity for high-risk tasks |
| `terse` | Cheap | Remove prose padding, apply substitution dictionary |
| `compact` | Precise | AST summaries: signatures + first docstring line, no bodies |
| `efficient` | Loop output | compact + terse + extended dict — maximum reduction |

`efficient` is the default for `opencontext loop` output. It chains:
1. **compact** — reduce code to signatures and docstrings
2. **terse** — compress prose to minimum form
3. **extended dictionary** — `function→fn`, `implementation→impl`, `service→svc`, `connection→conn`, `transaction→tx`, and more

Protected spans (code blocks, file paths, commands, errors, diffs, stack traces) are **never** modified.

Inter-agent handoffs also compress automatically — context dictionaries are compressed before passing between agents, reducing handoff token cost.

### AICX — Context Bytecode

AICX (Agent Incremental Context Exchange) is a compact, checksum-verified representation of an evidence plan — a transport/telemetry **side-channel** carried alongside the verified context. It encodes the plan as deduplicated references (with content inlined for protected evidence), giving you a tamper-evident fingerprint and a real token-reduction metric **without** stripping content from the context the agent actually receives.

```bash
$ opencontext bytecode compile --query "fix auth bug"

AICX/1
REQ id:2f8a2d6e surface:cli risk:normal budget:16000 q:q001
EVID id:file:exa src:s002 type:file conf:0.51 fresh:current tok:591 mode:handle
EVID id:symbol:e src:s004 type:symbol conf:0.33 fresh:current tok:47 mode:handle
...
CHK ed078856445c

instructions     : 15
evidence items   : 10
dictionary keys  : 12
original tokens  : 2654
bytecode tokens  : 242
token reduction  : 90.9%
checksum         : ✓ valid
```

```bash
opencontext bytecode compile --query "task"   # compile evidence plan to AICX
opencontext bytecode inspect [path]           # show metrics, gates, checksum
opencontext bytecode decode [path]            # reconstruct evidence plan (lazy)
```

---

## 🔒 Security

Secure by default. Nothing leaves your machine without explicit configuration.

| Surface | Default | Override |
|---------|---------|---------|
| External providers | ❌ Disabled | Enable per-provider in config |
| Network egress | ❌ Denied | `providers.external_enabled: true` |
| Secrets in prompts | ✅ Auto-redacted | Not configurable |
| MCP tools | ❌ Disabled | Allowlist required |
| Raw traces | ❌ Off | `traces.store_raw_context: true` |
| Missing policy | ✅ Fail closed | `fail_closed: false` |
| High-risk exports | ✅ Blocked by gate | `no-high-risk-exports` |

```bash
opencontext preset apply privacy     # Maximum privacy: air-gapped, fail-closed
opencontext security scan .          # Scan for secret leakage patterns
opencontext doctor security          # Full security audit
```

---

## 📊 Benchmark

Fully reproducible — run it yourself:

```bash
opencontext benchmark run
python -m pytest tests/core/test_comparative_benchmark.py -v -s
```

Results on OpenContext's own codebase:

| Task | Naive tokens | OpenContext | Reduction |
|------|------------:|------------:|----------:|
| Add `count_by_type()` to BridgeDetector | 49,394 | 2,474 | **95.0%** |
| Add `--json` flag to `bridges scan` | 59,363 | 2,273 | **96.2%** |
| Add RuntimeTrace persistence to WorkflowEngine | 27,556 | 6,905 | **74.9%** |
| **Average** | | | **88.7%** |

TDD compliance ✓ · Secrets clean ✓ on all three. The naive baseline grows as the
repo grows, so these are a snapshot — the numbers above are whatever the command
prints today.

*Naive baseline = all files in the relevant directory. Token estimate: `len(text)/4`. Run `pytest tests/core/test_comparative_benchmark.py -v -s` to reproduce.*

---

## 🔧 Configuration

```yaml
# opencontext.yaml

context_planning:
  enabled: true
  default_mode: progressive        # progressive | fast | minimal
  contract_required: true
  risk_classifier: deterministic
  max_expansion_rounds: 3

context:
  ranking:
    semantic_relevance: 0.25
    graph_centrality: 0.20
    call_distance: 0.15
    test_affinity: 0.10
    memory_confidence: 0.10
    recent_failure: 0.08
    risk_requirement: 0.07
    freshness: 0.03
    provenance: 0.02

memory:
  enabled: true
  provider: local                  # local | remote
  harvest_after_run: true
  decay:
    enabled: true
    default_half_life_days: 90

testing:
  mutation:
    enabled: false
    threshold: 80
    fail_on_low_score: false

context_storage:
  semantic_search: false           # enable for vector-powered retrieval

security:
  mode: private_project
  fail_closed: true

models:
  default:
    provider: mock                 # swap: anthropic / openai / openrouter / local
    model: mock-llm
```

### Presets

```bash
opencontext preset apply strict-tdd   # Enforce test-first across all phases
opencontext preset apply fast         # Cheap model, 2K budget, low latency
opencontext preset apply deep         # Premium model, 8K budget, max quality
opencontext preset apply privacy      # Air-gapped, fail-closed, no external calls
opencontext preset apply air-gapped   # Fully offline
```

---

## 🔌 Integrations

| Agent | Integration |
|-------|------------|
| Claude Code | MCP tools + AGENTS.md auto-generated |
| Cursor | `.cursorrules` + MCP config |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Windsurf | `.windsurfrules` |
| OpenCode / Kilo Code | MCP + agent profile |
| Any agent | `opencontext agent-context` emits reusable context block |

**MCP tools** (13 tools, pre-approved after `opencontext install`) — every read routed through the verified pipeline, every edit applied at symbol granularity:

```
# read (9)
opencontext_search    opencontext_context   opencontext_callers
opencontext_callees   opencontext_impact    opencontext_node
opencontext_files     opencontext_status    opencontext_trace

# symbol-level edits (4)
opencontext_replace_symbol_body   opencontext_insert_before_symbol
opencontext_insert_after_symbol   opencontext_rename_symbol
```

---

## 📚 CLI Reference

```bash
# Setup
opencontext install                              # Auto-detect, build graph, configure agent
opencontext install --yes                        # Non-interactive (CI)
opencontext doctor                               # Health check
opencontext update && opencontext upgrade

# Agentic Loop
opencontext loop --task "..." --flow full        # Interactive 8-phase SDD workflow
opencontext loop --task "..." --flow quick       # explore → apply → verify
opencontext loop --task "..." --flow autonomous  # No prompts, gates decide
opencontext loop --task "..." --max-rounds 3     # Retry on failure
opencontext loop --task "..." --compress efficient
opencontext loop --task "..." --dry-run          # Preview phases, no execution

# Context
opencontext index .
opencontext pack . --query "task" --copy
opencontext pack . --query "task" --format json
opencontext verified-context --query "task"
opencontext contract build --query "task"        # Show ContextContract YAML

# AICX Bytecode
opencontext bytecode compile --query "task"      # Compile to AICX bytecode
opencontext bytecode inspect [path]              # Show metrics and checksum
opencontext bytecode decode [path]               # Reconstruct evidence plan

# Knowledge Graph
opencontext knowledge-graph search "symbol"
opencontext knowledge-graph callers "func_name"
opencontext knowledge-graph impact "ClassName" --radius 2
opencontext knowledge-graph view --format tree

# SDD Harness
opencontext harness run --workflow sdd --task "description"
opencontext harness list

# Analysis
opencontext mutation run --scope changed --threshold 80
opencontext routes scan . --framework fastapi
opencontext bridges scan . --type HTTP --json
opencontext review --party --context "$(git diff HEAD~1)"
opencontext security scan .

# Memory
opencontext memory search --query "auth failures"
opencontext memory harvest
opencontext memory gc --dry-run

# Config
opencontext config wizard
opencontext preset list
opencontext preset apply <name>

# Plugins
opencontext plugin search
opencontext plugin install <name>

# Telemetry
opencontext telemetry show
opencontext benchmark run
```

---

## 🐍 Python SDK

```python
from opencontext_core import OpenContextRuntime

# Build a verified context pack
runtime = OpenContextRuntime()
runtime.setup_project(".")
prepared = runtime.prepare_context("Review authentication", max_tokens=6000)
# prepared.context   → compact, redacted, task-specific markdown
# prepared.trace_id  → auditable record of what was included and why

# Build a ContextContract
contract = runtime.build_contract("fix crash in auth middleware")
print(contract.risk_tier)        # "precise"
print(contract.token_budget)     # 16000
print([g.id for g in contract.must_verify])

# Run an agent programmatically
import asyncio
from pathlib import Path
from opencontext_core.agents import AGENT_REGISTRY
from opencontext_core.agents.base import AgentConfig

config = AgentConfig(
    name="tdd-enforcer",
    type="tdd-enforcer",
    objectives=["verify test suite passes"],
)
agent = AGENT_REGISTRY["tdd-enforcer"](config, Path("."))
result = asyncio.run(agent.execute())
print(result["cycle_status"])    # "green" | "red"
```

---

## 📖 Documentation

| Topic | Links |
|-------|-------|
| **Getting Started** | [Quickstart](docs/getting-started/quickstart.md) · [Installation](docs/getting-started/installation.md) · [Troubleshooting](docs/getting-started/troubleshooting.md) |
| **Architecture** | [Overview](docs/architecture/overview.md) · [Context Pack Builder](docs/architecture/context-pack-builder.md) · [Safety Layer](docs/architecture/safety-layer.md) |
| **Agentic Loop** | [Workflow Modes](docs/workflows/modes.md) · [Custom Workflows](docs/workflows/custom-workflows.md) |
| **SDD Workflow** | [SDD Guide](docs/workflows/sdd-workflow.md) · [Workflow Packs](docs/workflows/workflow-packs.md) |
| **Memory** | [Overview](docs/memory/overview.md) · [Session Harvesting](docs/memory/session-harvesting.md) · [Temporal Memory](docs/memory/temporal-memory.md) |
| **Compression** | [Overview](docs/token-efficiency/compression.md) · [Token Efficiency](docs/token-efficiency/overview.md) |
| **Configuration** | [Reference](docs/configuration/reference.md) · [Security Policy](docs/configuration/security-policy.md) |
| **Security** | [Threat Model](docs/security/threat-model.md) · [Data Classification](docs/security/data-classification.md) |
| **Integrations** | [Python SDK](docs/integrations/python-sdk.md) · [API](docs/integrations/api.md) · [GitHub Action](docs/integrations/github-action.md) |
| **Enterprise** | [Air-Gapped](docs/enterprise/air-gapped.md) · [Governance Reports](docs/enterprise/governance-reports.md) |
| **Development** | [Contributing](docs/development/contributing.md) · [Testing](docs/development/testing.md) · [Architecture Boundaries](docs/development/architecture-boundaries.md) |

---

## Install

| Method | Command |
|--------|---------|
| pip | `pip install opencontext-cli` |
| Linux/macOS | `curl -fsSL https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.sh \| bash` |
| Windows | `irm https://raw.githubusercontent.com/CesarMSFelipe/OpenContext-Runtime/main/install.ps1 \| iex` |
| Source | `git clone … && pip install -e packages/*` |

Requires **Python 3.12+**. No API key required for core functionality.

```bash
pytest                          # 1500+ tests
ruff check .                    # Lint
mypy packages/opencontext_core  # Types
```

---

MIT · [LICENSE](LICENSE) · [SECURITY.md](SECURITY.md) · [CONTRIBUTING.md](CONTRIBUTING.md)
