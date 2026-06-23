# CLI reference

OpenContext exposes 40+ commands. This page groups them by layer. For the
authoritative, always-current flags of any command, run:

```bash
opencontext <command> --help
```

Run `opencontext` with no arguments to open the navigable menu (settings and
tools in one place, no flags). Subcommand flags below are a guide — `--help` is
the source of truth.

## Setup & health

| Command | Purpose |
|---------|---------|
| `install` | Detect the stack, configure the editor, index the repo |
| `setup [<agent>…] [--all] [--dry-run] [--scope {global,local}]` | Configure agent client(s) — MCP + instructions/personas |
| `uninstall` | Remove OpenContext's managed config from agent client(s) |
| `sync` | Sync configuration and refresh managed assets |
| `stack` | Detect the stack and prepare agents with its engineering standards |
| `verify` | Component health checks |
| `doctor [security]` | Deep runtime diagnostics |
| `update` / `upgrade` | Check for / install a newer version |
| `clean` | Remove OpenContext data from the project |

## Context

| Command | Purpose |
|---------|---------|
| `explain "<task>"` | Why each file is (or isn't) in the context for a task |
| `pack . --query "<task>" [--copy]` | Token-aware context pack |
| `verified-context "<task>"` (alias `context`) | One-shot verified local context |
| `contract build --query "<task>"` | The ContextContract (risk tier, token budget, gates) |
| `index .` | Index a project root |
| `demo` | Token before/after on this repo |
| `tokens` | Token usage report |

## AICX bytecode

| Command | Purpose |
|---------|---------|
| `bytecode compile --query "<task>" [--json] [--save <path>]` | Compile a pack to AICX/1 bytecode (checksummed) |
| `bytecode inspect [<path>]` | Inspect a bytecode file |
| `bytecode decode <path>` | Decode round-trip |

## Code graph

| Command | Purpose |
|---------|---------|
| `knowledge-graph` (alias `kg`) `search` / `callers` / `callees` / `impact` / `node` | Query the code knowledge graph |
| `routes scan . --framework <fw>` | Detect framework routes |
| `bridges scan . --type <kind> [--json]` | Detect cross-language bridges |

## Agent loop & harness

| Command | Purpose |
|---------|---------|
| `clarify "<idea>"` | Turn a vague idea into a structured brief |
| `loop --task "…" --flow {quick,standard,full,quality} [--dry-run]` | Interactive agentic workflow loop with checkpoints |
| `harness run --workflow {sdd,explore-only,apply-only} --task "…"` | Execute a harness workflow |
| `harness list` / `harness report` | List workflow tracks / report a run |
| `workflow` | Workflow extension management |
| `preset apply <name>` | Apply a configuration preset |

Generative phases (spec, design, apply, …) need a configured provider or local
model; without one the harness stays honest planned-only. Inside an MCP host,
`opencontext_run` uses the host agent's model via MCP sampling.

## MCP & agent integration

| Command | Purpose |
|---------|---------|
| `mcp` | Start the MCP server (stdio) |
| `agent-context` | Emit a safe, reusable agent context block |
| `agent` | Agent tool integration files |
| `persona` | Inspect and configure OC personas |
| `models` / `profile` | Per-role / per-phase model assignment (delivered as MCP sampling hints) |

## Memory

| Command | Purpose |
|---------|---------|
| `memory {list,search,show,expand,collect,promote,demote,pin,unpin,prune,gc,maintain,review,doctor,export,import}` | Local memory (five layers; Engram coexistence is opt-in) |

## Governance & security

| Command | Purpose |
|---------|---------|
| `security scan .` | Scan for leaked secrets / risky artifacts |
| `privacy` | Manage privacy rules for the harness |
| `prompt {audit,export,sbom}` | Prompt safety lint / public-safe export / prompt-context SBOM |
| `release {audit,gate,evidence}` | Release leak audit, gate, and evidence |
| `ci-check run` | CI-friendly quality/health check |

## Config, plugins & optimization

| Command | Purpose |
|---------|---------|
| `config [wizard] [show]` | Configuration (also the navigable menu) |
| `plugin {search,install,update,info,list}` | Plugin management |
| `benchmark run` | Honest efficiency benchmark (OpenContext vs a grep+read control) |
| `skill` / `skill-registry` | AI skills and the skill registry |
