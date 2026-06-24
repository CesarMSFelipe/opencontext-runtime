<p align="center">
  <img src="docs/assets/logo.svg" alt="OpenContext" width="108" height="108">
</p>

<h1 align="center">OpenContext Runtime</h1>

<p align="center">
  <strong>Local control plane for AI software engineering agents.</strong>
</p>

<p align="center">
  Verified context · governed workflows · secure MCP tools · project memory<br>
  · quality gates · auditable receipts — across your existing coding agents.
</p>

<p align="center">
  One call. Call-graph-traced symbols. Verified context packs.<br>
  No grep loops. No whole-file read loops. No opaque vector guesses.
</p>

<p align="center">
  <a href="https://pypi.org/project/opencontext-cli/"><img src="https://img.shields.io/pypi/v/opencontext-cli?style=flat-square&color=00C9A7" alt="PyPI"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-00A8E8?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/license-MIT-gray?style=flat-square" alt="MIT">
</p>

<p align="center">
  <img src="docs/assets/runtime-strip.svg" alt="offline-first · call-graph traced · deterministic · MCP ready · claims tested" width="720">
</p>

<p align="center">
  <img src="docs/assets/hero-runtime.svg" alt="From agent request to verified context in one call: an AI coding agent asks; OpenContext Runtime traces the call graph, ranks symbols, locks a token budget and checks gates; a verified context pack is returned in one call" width="720">
</p>

<p align="center">
  <a href="#the-opencontext-difference">What It Does</a> ·
  <a href="#start-in-30-seconds">Quick Start</a> ·
  <a href="#proof-not-promises">Benchmarks</a> ·
  <a href="#the-context-runtime">How It Works</a> ·
  <a href="#local-code-graph">Code Graph</a> ·
  <a href="#agent-interface">MCP</a> ·
  <a href="#offline-by-default">Security</a> ·
  <a href="#installation">Install</a>
</p>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── THE WHOLE SYSTEM, AT A GLANCE ─────────────── -->

<div id="at-a-glance" align="center">

<table>
<tr>
<td width="760">

<h3>The whole system, at a glance</h3>

OpenContext is the layer **between your coding agent and your codebase** — it prepares verified context, runs a controlled agentic workflow, and keeps both governed. Everything below is one of these six pillars.

| Pillar | What it does |
|--------|--------------|
| **Context packs + code graph** | Call-graph-traced, token-budgeted context in one deterministic call — no grep loops, no full-file reads. |
| **Controlled SDD loop** | `explore → … → archive`, seven personas, gates and strict TDD — bounded and human-in-the-loop, not "go do everything". |
| **Your model, per persona** | Pick the model for each SDD phase in `opencontext.yaml`; it is sent to your agent as an MCP sampling hint. |
| **Persistent memory** | Local store by default (five layers); co-resident Engram coexistence is opt-in. Progressive, token-aware recall. |
| **Security by default** | Redaction, secret scanning, fail-closed posture, offline-first. |
| **19 MCP tools** | Search, context, call graph, impact, symbol edits, memory, quality — inside Claude Code, OpenCode, Codex. |

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── OFFLINE VS MODEL ─────────────── -->

<div id="offline-vs-model" align="center">

<table>
<tr>
<td width="760">

<h3>What runs offline — and what needs a model</h3>

OpenContext separates **local context operations** (always offline, deterministic — no LLM in the retrieval path) from **generative phases** (which need a model).

| Capability | Needs a model? | How it runs |
|---|---|---|
| Index, code graph, context packs, `explain`, `pack`, search, impact, routes, AICX bytecode | **No** | Fully offline, deterministic — same result every run |
| MCP read tools, the quality tool, memory search/context | **No** | Local MCP server over the indexed repo — deterministic |
| MCP `opencontext_run` (in-process agentic run) | **Host agent's model** | Via MCP sampling — your agent runs it on its own model; zero provider or API-key config on the OpenContext side |
| Standalone `opencontext loop` / `harness run` generative phases (spec, design, apply, …) | **Yes** | A configured provider or local model (e.g. ollama). Without one the harness stays **honest planned-only** — it emits a structured plan for your agent to complete; it never fakes a result |

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/offline-model-matrix.svg" alt="What runs offline vs needs a model: local context ops and MCP read/quality/memory tools are offline and deterministic; opencontext_run uses the host agent's model via MCP sampling; standalone generative phases need a provider or run planned-only" width="720">
</p>

<p align="center">
  <sub>Offline by default · only generative phases need a model · <code>opencontext_run</code> borrows the host agent's model via sampling</sub>
</p>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<p align="center">
  <img src="docs/assets/demo-terminal.svg" alt="Real opencontext explain output on tiangolo/fastapi — task: add OAuth2 bearer token auth — a verified pack in one call instead of a grep/read loop" width="720">
</p>

<p align="center">
  <sub>Real output · tiangolo/fastapi · one call replaces a multi-round grep+read loop</sub>
</p>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── THE OPENCONTEXT DIFFERENCE ─────────────── -->

<div id="the-opencontext-difference" align="center">

<table>
<tr>
<td width="760">

<h3>The OpenContext Difference</h3>

AI coding agents usually discover context through repeated search and full-file reads. Each file read whole. Call direction invisible. Results vary between runs.

**OpenContext builds the context before the agent starts.** Traces the call graph, ranks symbols, applies a token budget, delivers a verified pack in one deterministic call.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/difference-card.svg" alt="OpenContext flow: 01 Trace Graph → 02 Rank Symbols → 03 Apply Budget → 04 Verified Pack. Built before the agent starts. Same result every run." width="720">
</p>

<p align="center">
  <sub>Runtime · deterministic pipeline · no LLM in the retrieval path · same result every run</sub>
</p>

<p align="center">
  <img src="docs/assets/before-after.svg" alt="Without OpenContext: agent grep+read loop over many rounds, no call graph. With OpenContext: far fewer tokens, one call, call graph traced." width="720">
</p>

<p align="center">
  <sub>Benchmark · tiangolo/fastapi · add OAuth2 auth · far fewer tokens, one call instead of a grep/read loop</sub>
</p>

<p align="center">
  <img src="docs/assets/workflow-audience.svg" alt="Built for: agent users, large repositories, structured SDD workflows, security-first teams" width="720">
</p>

<p align="center">
  <sub>Not a good fit: repos under ~50 files, or workflows that specifically require semantic embedding search.</sub>
</p>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── START IN 30 SECONDS ─────────────── -->

<div id="start-in-30-seconds" align="center">

<table>
<tr>
<td width="760">

<h3>Start in 30 Seconds</h3>

Run the demo on your actual repository, then wire OpenContext into your editor.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/quickstart-flow.svg" alt="01 install → 02 run demo → 03 configure editor → 04 editor ready" width="720">
</p>

<p align="center">
  <sub>Setup · pip install → demo on your repo → editor wizard → MCP wired</sub>
</p>

<div align="center">

<table>
<tr>
<td width="760">

```bash
pipx install opencontext-cli   # recommended — isolated, on PATH
cd your-project
opencontext install            # stack detection · editor setup · index repo
opencontext demo               # see the token + call reduction on your repo
```

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── PROOF, NOT PROMISES ─────────────── -->

<div id="proof-not-promises" align="center">

<table>
<tr>
<td width="760">

<h3>Proof, Not Promises</h3>

Every benchmark runs on a public repository. No hidden dataset. No hosted service. No benchmark-only path. Fully reproducible with `opencontext explain`.

**Benchmark methodology:** "Agent loop" means reading full files discovered via grep-style search, without call-graph tracing. OpenContext returns one verified pack from `opencontext explain` on the same public repositories — far fewer tokens, one call instead of a grep/read loop. We make no fixed percentage claim: completeness and latency are measured directly by the honest efficiency benchmark (`opencontext benchmark`), and real agent behavior varies by model, editor, and tool strategy.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/stats-bar.svg" alt="far fewer tokens · many rounds to one call · call graph included · deterministic" width="720">
</p>

<p align="center">
  <img src="docs/assets/benchmark-card-requests.svg" alt="psf/requests — fix retry bug: grep+read over several rounds vs opencontext one call — far fewer tokens" width="720">
</p>

<p align="center">
  <sub>Benchmark · psf/requests · retry bug · <code>send → RetryError</code> surfaced by call graph, not query text</sub>
</p>

<p align="center">
  <img src="docs/assets/benchmark-card-fastapi.svg" alt="tiangolo/fastapi — add OAuth2 auth: grep+read over many rounds vs opencontext one call — far fewer tokens" width="720">
</p>

<p align="center">
  <sub>Benchmark · tiangolo/fastapi · OAuth2 auth · <code>routing.py</code> is 56,550 tokens — OpenContext returns only the symbols that matter</sub>
</p>

<p align="center">
  <img src="docs/assets/benchmark-numbers.svg" alt="4 public-repo benchmarks: retry bug, SSL verify, OAuth2 auth, project overview — grep+read loop vs one OpenContext call, far fewer tokens" width="720">
</p>

<p align="center">
  <sub>Numbers · 4 public repos · agent loop = full files via grep, no call graph · all reproducible</sub>
</p>

<div align="center">

<table>
<tr>
<td width="760">

When a file exceeds the per-item budget, OpenContext is explicit — it never silently drops content:

```
Kept out (and why):
  ✗ django/db/models/query.py   29,532 tok — item_exceeds_available_budget
```

Pass `--max-tokens 32000` (or raise `context.max_input_tokens` in `opencontext.yaml`) to include it.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── THE CONTEXT RUNTIME ─────────────── -->

<div id="the-context-runtime" align="center">

<table>
<tr>
<td width="760">

<h3>The Context Runtime</h3>

Every query runs through a deterministic pipeline. A **ContextContract** locks in the token budget, required symbols, and verification gates _before_ retrieval starts.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/pipeline.svg" alt="OpenContext pipeline: query → classify → ContextContract → retrieve → score → pack → gates → deliver" width="720">
</p>

<p align="center">
  <sub>Runtime · deterministic · no LLM in retrieval · offline</sub>
</p>

<div align="center">

<table>
<tr>
<td width="760">

**Command**
```bash
opencontext contract build --query "fix crash in auth middleware"
```

**Output**
```yaml
task: fix crash in auth middleware
task_type: bugfix
risk_tier: precise
token_budget: 16000
required_symbols: ['*crash*', '*auth*', '*middleware*']
must_verify: [run-tests, lint, type-check]
```

**Risk Tiers**

| Risk Tier | Token Budget | When |
|-----------|-------------|------|
| `cheap` | 8,000 | Renames, docs, trivial fixes |
| `precise` | 16,000 | Bugfixes, features, refactors |
| `critical` | 28,000 | Security, migrations, architecture |

**AICX Bytecode**

Context packs are serialized as AICX bytecode — compact, verifiable, with a cryptographic checksum. Agents can validate integrity before acting.

```bash
opencontext bytecode compile --query "fix auth bug"
opencontext bytecode inspect
opencontext bytecode decode <path.aicx>
```

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── LOCAL CODE GRAPH ─────────────── -->

<div id="local-code-graph" align="center">

<table>
<tr>
<td width="760">

<h3>Local Code Graph</h3>

SQLite + FTS5, fully offline. Indexes symbols, call chains, imports, and framework routes. Python works out of the box; TypeScript, JavaScript, Go, Rust, Java, and PHP add full symbol extraction once their tree-sitter grammar is installed (`pip install tree-sitter-typescript`, etc.). Files in any language are still indexed and searchable.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/local-code-graph.svg" alt="Graph layers: files → symbols → imports + call graph → routes → bridges. Index once, query offline." width="720">
</p>

<p align="center">
  <sub>Code Graph · 6 layers · symbol-level · cross-language bridges · offline</sub>
</p>

<div align="center">

<table>
<tr>
<td width="760">

**Real output on psf/requests**
```
Why this context — how does authentication work
20 files · 9,900 tokens

src/requests/auth.py:116     0.86  125  graph · class HTTPProxyAuth  · matched query
src/requests/auth.py:85      0.84  362  graph · class HTTPBasicAuth  · matched query
src/requests/sessions.py     0.83  385  graph · method rebuild_auth  · matched query
src/requests/models.py       0.73   81  graph · method prepare_auth  · calls:HTTPBasicAuth
docs/user/authentication.rst 0.68 1464  manifest
```

`prepare_auth → HTTPBasicAuth` surfaced from the call graph — not from the query text.

```bash
opencontext index .
opencontext explain "how does authentication work"
opencontext knowledge-graph callers "authenticate_user"
opencontext knowledge-graph impact "UserModel" --radius 2
opencontext routes scan . --framework fastapi
opencontext bridges scan . --type HTTP --json
```

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── AGENT INTERFACE ─────────────── -->

<div id="agent-interface" align="center">

<table>
<tr>
<td width="760">

<h3>Agent Interface</h3>

19 MCP tools. OpenContext ships adapters for 20+ agent clients (Claude Code, OpenCode, Cursor, Copilot, Windsurf, Codex, Gemini CLI, Zed, Aider, Cline, and more). Support level varies by client — some get MCP + instruction files, others get documented setup patterns.

`opencontext install` writes seven OC personas to your editor's agents directory. In OpenCode, press **Tab** to switch to one. In Claude Code, they appear as subagents. Each SDD phase runs as the persona suited to it.

| Persona | SDD phase | Role |
|---------|-----------|------|
| **OC Orchestrator** | propose · spec · tasks | Thin coordinator: plans, delegates, and verifies through the gates. Delegates reading 4+ files, writing 2+ files, and every commit to a focused sub-step. |
| **OC Explorer** | explore | Investigates the codebase: maps the territory before any change via the knowledge graph. |
| **OC Architect** | design | Designs the technical approach: architecture, components, data flow. |
| **OC Builder** | apply | Implements the design: writes code that matches existing patterns. |
| **OC Tester** | test | Senior QA: writes behavior tests that fail when the code breaks. |
| **OC Reviewer** | verify · review | Rigorous reviewer: code review (one finding per line), quality gates, adversarial review. |
| **OC Professor** | — | Teaching mentor: explains the why and the concept before the code, grounded in your real code. |

**Multi-agent execution:** the OC Orchestrator is a thin coordinator — it never does all the work itself. Reading, writing, and verifying are always delegated to specialized sub-agents. When you run the harness, each phase runs in its own context: explore → propose → spec → design → tasks → apply → verify → review → archive. Phases that can run in parallel do.

<h3>Runs on top of your agent — you choose the model per persona</h3>

OpenContext is the agentic system **on top of** your coding agent, not another agent CLI. Your agent (Claude Code, Codex, OpenCode, …) **fixes the provider**: when OpenContext needs a generation it asks your agent to run it on the agent's own model via MCP sampling — **zero provider or API-key config** on the OpenContext side.

What you control is **which model each unit of work uses** — declared in `opencontext.yaml` and sent to your agent as an MCP `modelPreferences` hint. Anything unset uses your agent's own model; nothing is chosen for you:

```yaml
# opencontext.yaml — pick the model per SDD phase (the provider is always your agent's)
models:
  phases:
    explore: { model: haiku }    # cheap where it doesn't matter
    design:  { model: opus }     # strong where it does
    apply:   { model: sonnet }
  roles:                         # optional second axis: functional ops + MCP tools
    classify: { model: haiku }
```

Two independent axes, both delivered as sampling hints: **phases** (≙ personas: Architect → design, Explorer → explore, Builder → apply, …) drive the SDD harness; **roles** (classify / retrieve / rerank / generate / …) drive the runtime and MCP tools. At install you pick a preset (`default` / `cheap` / `hybrid` / `premium`) that writes this block for you; a command shortcut also exists (`opencontext models set-persona architect opus`) — it just edits the same file. (Prefer OpenContext to run a model itself? Set a real provider per role; local providers like ollama work too.)

> **After `opencontext install`:** reload your shell (`source ~/.bashrc`) if PATH changed, then **restart your agent** so it loads the OpenContext MCP server.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/mcp-tools.svg" alt="19 MCP tools: 9 read tools (search, context, callers, callees, impact, node, files, status, trace), 4 symbol-level edit tools, an in-process agentic run tool, 4 memory tools (save, search, context, judge), and 1 architecture-quality tool" width="720">
</p>

<p align="center">
  <sub>Agent Interface · 19 MCP tools · 9 read + 4 symbol-level edits + 1 agentic run + 4 memory + 1 quality</sub>
</p>

<div align="center">

<table>
<tr>
<td width="760">

```bash
opencontext setup claude-code
opencontext setup cursor
opencontext setup --all
```

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── AGENTIC HARNESS ─────────────── -->

<div id="agentic-harness" align="center">

<table>
<tr>
<td width="760">

<h3>Agentic Harness</h3>

The execution harness runs structured multi-agent workflows. Each phase is isolated: it reads what it needs, does its work, passes gates, then hands off. No phase can skip a gate.

**Generative phases need a model.** Inside an MCP host, `opencontext_run` uses the host agent's model via sampling — no key needed. Standalone (`opencontext loop` / `harness run`) needs a configured provider or local model; without one the harness stays honest planned-only — it emits a structured plan, never fakes output.

```bash
opencontext clarify "add OAuth2 login"
opencontext loop --task "..." --flow full
opencontext loop --task "..." --flow quality
opencontext loop --task "..." --flow quick --dry-run
```

| Track | Phases | When |
|-------|--------|------|
| `quick` | explore → apply → verify | Simple fixes |
| `standard` | explore → propose → spec + design → apply → verify | Features, refactors |
| `full` | All 9 phases | Architecture, security |
| `autonomous` | All 9, no prompts | CI/CD, automation |
| `quality` | All 9 + GGA rules + judgment | Maximum quality gates |

**Phases:** `explore → propose → spec → design → tasks → apply → verify → review → archive`

The base flow ends with `review` (the final quality gate) then `archive`. The `quality` track appends an extra `judgment` phase — adversarial structural review of apply artifacts (missing files, failed gates, missing verify) — and enforces GGA rules before it.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/sdd-phases.svg" alt="SDD 9-phase workflow: explore, propose, spec, design, tasks, apply, verify, review, archive. Quality track adds GGA rules and judgment phases." width="720">
</p>

<p align="center">
  <sub>SDD Workflow · 9 phases · blue = works without LLM · amber dashes = optional quality gates</sub>
</p>

<p align="center">
  <img src="docs/assets/tdd-phases.svg" alt="TDD workflow: explore (offline), write test (red — failing), implement, verify (green — passing), refactor, verify (offline). Repeat write test → verify until green." width="720">
</p>

<p align="center">
  <sub>TDD Workflow · test first · implement minimum · verify green · refactor · verify again</sub>
</p>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── OFFLINE BY DEFAULT ─────────────── -->

<div id="offline-by-default" align="center">

<table>
<tr>
<td width="760">

<h3>Offline by Default</h3>

Knowledge graph, context packing, MCP tools, and benchmarks run without external services. Index your repo once; every query after that is local.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/security-defaults.svg" alt="Security defaults: external providers disabled, secrets auto-redacted, MCP tools blocked until allow-listed, missing policy fail closed" width="720">
</p>

<p align="center">
  <sub>Security · 4 defaults active out of the box · no configuration required</sub>
</p>

<div align="center">

<table>
<tr>
<td width="760">

```bash
opencontext security scan .
opencontext doctor security
opencontext preset apply privacy    # air-gapped · fail-closed · no egress
```

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── INSTALLATION ─────────────── -->

<div id="installation" align="center">

<table>
<tr>
<td width="760">

<h3>Installation</h3>

**Requirements:** Python 3.12+

```bash
pipx install opencontext-cli      # recommended — isolated, always on PATH
```

Other options — `pip`, `uv`, the `curl` / PowerShell bootstrap scripts, and the portable `.pyz` binary — are in the [installation guide](docs/getting-started/installation.md).

After installing, run the setup wizard in your project:

```bash
cd your-project
opencontext install     # detects editor, writes MCP config, indexes repo
opencontext verify      # confirm all checks pass
opencontext doctor      # deep diagnostics if something looks wrong
```

`opencontext install` auto-detects Claude Code, OpenCode, Cursor, Copilot, Windsurf, and more. It writes MCP config and the seven OC personas (Orchestrator, Explorer, Architect, Builder, Tester, Reviewer, Professor) to your editor's agents directory.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── LOCAL AGENT MEMORY ─────────────── -->

<div align="center">

<table>
<tr>
<td width="760">

<h3>Local Agent Memory</h3>

Five layers, SQLite + FTS5, zero external services. Past failures automatically surface first in the next run.

| Layer | Stores |
|-------|--------|
| `SEMANTIC` | Stable project facts |
| `EPISODIC` | Past task outcomes |
| `PROCEDURAL` | Learned rules |
| `WORKING` | Current task context |
| `FAILURE` | Symbols that caused test failures |

```bash
opencontext memory search "auth middleware"
opencontext memory collect
opencontext memory review
opencontext memory gc --dry-run
```

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── WORKFLOW SKILLS ─────────────── -->

<div align="center">

<table>
<tr>
<td width="760">

<h3>Workflow Skills</h3>

Drop `.skill.md` files in `skills/`. OpenContext injects the right ones based on file extensions and task keywords.

| Skill | Injected When |
|-------|--------------|
| `fix` | Task mentions "bug", "fix", "crash", "regression" |
| `prd` | Task is a vague idea before SDD |
| `work-unit-commits` | Any apply phase |
| `oc-onboard` | First run on a new project |

```bash
opencontext skill-registry refresh
```

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── RUNTIME COMMANDS ─────────────── -->

<div align="center">

<table>
<tr>
<td width="760">

<h3>Core commands</h3>

The everyday commands, grouped by layer. The full surface (40+ commands) lives in the [CLI reference](docs/reference/cli.md).

| Layer | Main commands | When |
|-------|---------------|------|
| Setup | `install` · `setup` · `verify` · `doctor` | First run + agent integration |
| Context | `explain` · `pack` · `verified-context` · `contract` | Before coding |
| Code graph | `index` · `knowledge-graph` · `routes` · `bridges` | Understand impact |
| Agent loop | `clarify` · `loop` · `harness run` | Structured SDD/TDD workflows |
| MCP | `mcp` · `agent-context` | Agent integrations |
| Governance | `security` · `privacy` · `prompt` · `release` · `ci-check` | Safe usage + CI |
| Memory | `memory` | Reuse project knowledge |
| Optimization | `benchmark` · `tokens` · `bytecode` | Measure + reduce context cost |

Run `opencontext` with no arguments for the navigable menu — settings and tools in one place, no flags.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── STATUS, LIMITS & CLAIMS ─────────────── -->

<div id="maturity" align="center">

<table>
<tr>
<td width="760">

<h3>Maturity &amp; status</h3>

Production-oriented local runtime. The context, code-graph, MCP, and memory paths are implemented and exercised by the test suite. Some capabilities are scaffolded or fail-closed by design and must be explicitly enabled by policy. Certification-grade enterprise posture is not claimed.

| Status | Examples |
|--------|----------|
| **Stable** | Index, code graph, context packs, MCP read tools, local memory |
| **Opt-in** | Engram memory coexistence, external LLM providers, MCP symbol-edit tools, semantic/vector search |
| **Host-agent dependent** | `opencontext_run` and standalone generative phases — need the host model (MCP sampling) or a configured provider |
| **Scaffolded / fail-closed** | Network egress, tool forwarding, raw-trace storage — denied unless policy enables them |

<h3>Known limitations</h3>

- Best on repos above ~50 files; tiny repos see little benefit.
- Full symbol extraction needs the language's tree-sitter grammar (Python works out of the box; others after `pip install tree-sitter-<lang>`). Files in any language are still indexed and searchable.
- Standalone generative phases need a provider or local model; without one they run planned-only.
- No semantic/embedding search by default — deterministic graph + FTS only. A deliberate choice, not an oversight.
- Windows is exercised in CI but is not the primary development target.

<h3>README claims are tested</h3>

The quantified claims here are guarded by end-to-end smoke tests that drive the real CLI/SDK — no mocks:

```bash
pytest tests/smoke/test_readme_claims.py -v
```

They check the contract risk tiers and token budgets, the AICX bytecode round-trip, the loop dry-run phases, the SDK contract, and that the README's MCP-tool count matches the running server. Benchmarks are reproducible with `opencontext benchmark run`; the README makes no fixed percentage claim.

</td>
</tr>
</table>

</div>

<p align="center">
  <img src="docs/assets/release-trust.svg" alt="Release 1.5.0 status: stable — code graph, context packs, MCP read tools, local memory; opt-in — Engram, external providers, symbol-edit tools, semantic search; host-agent dependent — opencontext_run and standalone generative phases; scaffolded and fail-closed — egress, tool forwarding, raw traces. Claims guarded by pytest tests/smoke/test_readme_claims.py" width="720">
</p>

<p align="center">
  <sub>Status · stable / opt-in / host-dependent / fail-closed · every quantified claim guarded by a smoke test</sub>
</p>

<p align="center">
  <img src="docs/assets/divider.svg" alt="" width="720">
</p>

<!-- ─────────────── DOCS INDEX ─────────────── -->

<div align="center">

<table>
<tr>
<td width="760">

<h3>Documentation</h3>

| Area | Links |
|------|-------|
| Getting Started | [Quickstart](docs/getting-started/quickstart.md) · [Installation](docs/getting-started/installation.md) · [Troubleshooting](docs/getting-started/troubleshooting.md) |
| Reference | [CLI commands](docs/reference/cli.md) |
| Configuration | [TUI Menu](docs/configuration/tui-menu.md) · [Walkthrough](docs/configuration/walkthrough.md) · [Reference](docs/configuration/reference.md) · [User Config](docs/configuration/user-config.md) |
| Architecture | [Overview](docs/architecture/overview.md) · [Context Pack Builder](docs/architecture/context-pack-builder.md) · [Safety Layer](docs/architecture/safety-layer.md) |
| Workflows | [Flow Modes](docs/workflows/modes.md) · [SDD Guide](docs/workflows/sdd-workflow.md) · [Custom Workflows](docs/workflows/custom-workflows.md) |
| Security | [Threat Model](docs/security/threat-model.md) · [Data Classification](docs/security/data-classification.md) |
| Integrations | [Python SDK](docs/integrations/python-sdk.md) · [API](docs/integrations/api.md) · [GitHub Action](docs/integrations/github-action.md) · [Air-Gapped](docs/enterprise/air-gapped.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) · [Architecture deep-dive](docs/architecture/overview.md) |

</td>
</tr>
</table>

</div>

<br>

<p align="center">
  <img src="docs/assets/footer-mark.svg" alt="OpenContext Runtime — Small context. Full trace. Verified execution." width="720">
</p>

<p align="center">
  <sub>MIT · <a href="LICENSE">LICENSE</a> · <a href="SECURITY.md">SECURITY.md</a> · <a href="CONTRIBUTING.md">CONTRIBUTING.md</a></sub>
</p>
