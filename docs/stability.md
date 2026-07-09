# Stability: Stable vs Experimental Surface Map

This page publishes the public surface of OpenContext — CLI commands, MCP tools,
and workflows — grouped by stability tag. It is derived directly from the
source-of-truth tables in code, not from a hand-maintained list:

- CLI commands: `packages/opencontext_cli/opencontext_cli/contracts/command_registry.py`
  (`COMMAND_MATURITY`) — the canonical Sprint 2 truth layer that both
  `opencontext maturity` and the `--help` `(preview)` policy read.
- MCP tools: `packages/opencontext_core/opencontext_core/mcp_stdio.py`
  (the safe-by-default allowlist `_default_tool_names`, `WORKFLOW_TOOL_NAMES`,
  and the symbol-write handlers behind approval gates).
- Workflows: `packages/opencontext_core/opencontext_core/workflows/registry.py`
  and `workflows/aliases.py` (`WORKFLOW_ALIASES`).

## What each tag promises

| Tag | Promise |
|-----|---------|
| **stable** | Supported surface. Documented behavior you can rely on; breaking changes only land on a major version bump. |
| **beta** | Works today, but the interface is still evolving and may change between minor versions without a major bump. Opt-in tools that write state also land here. |
| **experimental** | Internal / dev / debug / legacy plumbing. No stability contract — may change or disappear at any time, and is hidden from the primary `--help`. |

Tag mapping from the source maturity levels:

- CLI: `stable → stable`, `preview → beta`, `internal → experimental`.
- MCP: safe-by-default read/memory tools `→ stable`; opt-in session/run tools
  and approval-gated symbol-write tools `→ beta`.
- Workflows: the core SDD tracks `→ stable`, the SDD phase subsets `→ beta`,
  the derived quality/judgment tracks `→ experimental`.

---

## CLI commands

Derived from `COMMAND_MATURITY` in `contracts/command_registry.py`. Aliases point
at their canonical command (`kg → knowledge-graph`, `context → verified-context`).

### stable

| Command | Tag | Note |
|---------|-----|------|
| `clean` | stable | Remove generated OpenContext state. |
| `config` | stable | Configuration menu and management. |
| `doctor` | stable | Deep runtime diagnostics. |
| `harness` | stable | Agent harness controls. |
| `index` | stable | Index the project into the knowledge graph. |
| `init` | stable | Create project config. |
| `install` | stable | Full project setup. |
| `knowledge-graph` | stable | Query the semantic knowledge graph. |
| `memory` | stable | Memory store CLI (search/save/context). |
| `pack` | stable | Generate a task-scoped context pack. |
| `run` | stable | Run an operational task with OC Flow. |
| `runs` | stable | Inspect persisted harness runs. |
| `sdd` | stable | Spec-Driven Development track. |
| `status` | stable | Show project status. |
| `tui` | stable | Terminal UI (doctor, config, uninstall). |
| `uninstall` | stable | Remove OpenContext from a workspace. |
| `version` | stable | Print the installed version. |

### beta

| Command | Tag | Note |
|---------|-----|------|
| `agent` | beta | Agentic engineering entry point. |
| `agent-harness` | beta | Agent harness plumbing (evolving). |
| `agents` | beta | Agents scope: AI agent client config. |
| `architecture` | beta | Architecture inspection. |
| `benchmark` | beta | Run efficiency / context-coverage benchmarks. |
| `bridges` | beta | Integration bridges. |
| `capabilities` | beta | Report detected project and runtime capabilities. |
| `clarify` | beta | Clarify an ambiguous task before running it. |
| `context` | beta | Alias of `verified-context`. |
| `contract` | beta | Contract inspection. |
| `decision-log` | beta | Decision log surface. |
| `decisions` | beta | Decisions surface. |
| `demo` | beta | Run a guided demo of OpenContext. |
| `engram` | beta | Engram persistent-memory bridge. |
| `explain` | beta | Explain a symbol, decision, or route. |
| `health` | beta | Read-only health summary. |
| `kg` | beta | Alias of `knowledge-graph`. |
| `loop` | beta | Run the standalone agent loop. |
| `maturity` | beta | List per-command API maturity. |
| `mcp` | beta | Start the MCP server for agent integration. |
| `models` | beta | Inspect and manage model routing. |
| `oc-new` | beta | Start a new SDD change (OC Flow). |
| `persona` | beta | Persona selection and management. |
| `plugin` | beta | Plugin ecosystem management. |
| `policy` | beta | Policy inspection and simulation. |
| `preset` | beta | Preset management. |
| `privacy` | beta | Privacy / redaction controls. |
| `product` | beta | Product scope: the OpenContext installation itself. |
| `profile` | beta | Profile inspection. |
| `prompt` | beta | Prompt inspection and management. |
| `receipt` | beta | Inspect and export run receipts. |
| `review` | beta | Review helpers. |
| `routes` | beta | Route inspection. |
| `security` | beta | Security posture and checks. |
| `session` | beta | Operate over runtime sessions (list/status/resume/archive). |
| `setup` | beta | Interactive project setup. |
| `simulate` | beta | Preview a task (workflow, policy, cost) without running it. |
| `skill` | beta | Skill management. |
| `skill-registry` | beta | Index available skills by trigger and path. |
| `stack` | beta | Stack detection. |
| `storage` | beta | Storage inspection. |
| `studio` | beta | Studio surface. |
| `sync` | beta | Sync artifacts and issues. |
| `telemetry` | beta | Telemetry controls. |
| `tokens` | beta | Token accounting and budgets. |
| `update` | beta | Check for a newer version. |
| `upgrade` | beta | Install the latest version. |
| `verified-context` | beta | Build verified, minimal context for a task. |
| `verify` | beta | Run component health checks. |
| `workspace` | beta | Workspace scope: this repo's OpenContext state. |

### experimental

| Command | Tag | Note |
|---------|-----|------|
| `agent-context` | experimental | Agent-facing context surface (dev). |
| `aicx` | experimental | AI-context lockfile plumbing (dev). |
| `approvals` | experimental | Approval-gate plumbing. |
| `ask` | experimental | Ad-hoc ask (dev). |
| `bytecode` | experimental | Bytecode-level analysis (dev). |
| `cache` | experimental | Cache management (dev). |
| `checkpoint` | experimental | Checkpoint plumbing. |
| `ci-check` | experimental | CI-check plumbing (dev). |
| `command` | experimental | Raw command plumbing. |
| `eval` | experimental | Structural eval runner (dev). |
| `evolve` | experimental | Evolution / migration plumbing. |
| `extension` | experimental | Extension plumbing. |
| `git` | experimental | Git plumbing helpers. |
| `hints` | experimental | Task-hint plumbing. |
| `inspect` | experimental | Low-level inspection (dev). |
| `instructions` | experimental | Instruction plumbing. |
| `learn` | experimental | Learning / feedback plumbing. |
| `mutation` | experimental | Mutation analysis (dev). |
| `onboard` | experimental | Onboarding walkthrough (dev). |
| `org` | experimental | Org baseline plumbing. |
| `playbooks` | experimental | Playbook plumbing. |
| `provider` | experimental | Provider plumbing. |
| `quality` | experimental | Quality gate plumbing. |
| `release` | experimental | Release plumbing. |
| `report` | experimental | Report plumbing. |
| `trace` | experimental | Trace plumbing. |
| `watch` | experimental | File-watch plumbing. |
| `workflow` | experimental | Workflow plumbing. |
| `workflows` | experimental | Legacy workflows plumbing. |

---

## MCP tools

Derived from `mcp_stdio.py`. The safe-by-default allowlist (`_default_tool_names`)
is what a vanilla MCP server exposes — read-only and memory tools — so it is
**stable**. Tools that write session state or run harnesses (`WORKFLOW_TOOL_NAMES`)
and the symbol-write tools (behind an explicit policy opt-in and an
`approval_required` gate) are **beta**: they work, but require opt-in and can
mutate state, so their contract is not frozen.

### stable (safe-by-default read + memory tools)

| Tool | Tag | Note |
|------|-----|------|
| `opencontext_search` | stable | Find symbols by name. |
| `opencontext_context` | stable | Build task-relevant code context. |
| `opencontext_callers` | stable | Trace who calls a function. |
| `opencontext_callees` | stable | Trace what a function calls. |
| `opencontext_impact` | stable | Impact / blast-radius before editing. |
| `opencontext_node` | stable | Get a single symbol's details. |
| `opencontext_files` | stable | Indexed file structure. |
| `opencontext_status` | stable | Index health status. |
| `opencontext_trace` | stable | Trace a path between symbols. |
| `opencontext_memory_save` | stable | Save a memory observation. |
| `opencontext_memory_search` | stable | Search memory observations. |
| `opencontext_memory_context` | stable | Recent memory context. |
| `opencontext_memory_judge` | stable | Judge / relate a memory candidate. |
| `opencontext_quality` | stable | Read-only quality diff. |
| `opencontext_session_inspect` | stable | Read-only session inspection. |
| `opencontext_session_status` | stable | Read-only session status. |
| `opencontext_workflow_list` | stable | List workflows (read-only meta). |
| `opencontext_workflow_explain` | stable | Explain a workflow (read-only meta). |
| `opencontext_profile_list` | stable | List profiles (read-only meta). |
| `opencontext_profile_explain` | stable | Explain a profile (read-only meta). |
| `opencontext_doctor` | stable | Runtime diagnostics (read-only). |

### beta (opt-in session/run tools + approval-gated writes)

| Tool | Tag | Note |
|------|-----|------|
| `opencontext_run` | beta | Drive the agentic harness; opt-in, writes run state. |
| `opencontext_session_start` | beta | Start a session; opt-in, writes session state. |
| `opencontext_session_next` | beta | Advance to the next session step; opt-in. |
| `opencontext_session_observe` | beta | Record an observation on a session; opt-in. |
| `opencontext_session_apply` | beta | Apply a session step; opt-in, writes state. |
| `opencontext_session_resume` | beta | Resume a session; opt-in, writes state. |
| `opencontext_session_archive` | beta | Archive a session (terminal); opt-in. |
| `opencontext_replace_symbol_body` | beta | Symbol write; policy opt-in + approval gate. |
| `opencontext_insert_before_symbol` | beta | Symbol write; policy opt-in + approval gate. |
| `opencontext_insert_after_symbol` | beta | Symbol write; policy opt-in + approval gate. |
| `opencontext_rename_symbol` | beta | Symbol rename; policy opt-in + approval gate. |

---

## Workflows

Derived from `workflows/registry.py` (registered definitions `sdd` and the
derived `sdd-quality`) and `workflows/aliases.py` (`WORKFLOW_ALIASES`). The core
SDD tracks and its phase subsets are the supported planning surface; the
quality/judgment tracks resolve onto the derived `sdd-quality` definition and are
legacy/experimental.

| Workflow | Tag | Note |
|----------|-----|------|
| `sdd` | stable | Core Spec-Driven Development track (explore → … → archive). |
| `explore-only` | beta | SDD phase subset: explore only, resolves onto the `sdd` definition. |
| `apply-only` | beta | SDD phase subset: apply only, resolves onto the `sdd` definition. |
| `full+judgment` | experimental | Legacy track: adds judgment phases; resolves onto derived `sdd-quality`. |
| `full+gga` | experimental | Legacy track: adds GGA phases; resolves onto derived `sdd-quality`. |
| `full+quality` | experimental | Legacy track: adds quality phases; resolves onto derived `sdd-quality`. |

---

## Resolved: single source of truth for command maturity

Both user-facing maturity signals now read the **same** table — the canonical
Sprint 2 truth layer at `contracts/command_registry.py` (`COMMAND_MATURITY`,
17 stable):

- `opencontext --help` — `main._apply_maturity_help_policy` reads it to hide
  internal commands and append the `(preview)` marker to preview commands.
- `opencontext maturity commands` — `maturity_cmd._commands_report` reads it to
  list every command's `stable`/`preview`/`internal` level.

Previously the `maturity` command imported a *second*, wider `COMMAND_MATURITY`
from `command_maturity.py` (49 stable), so it reported `mcp`, `verify`, and
`session` as **stable** while `--help` marked the same commands `(preview)` —
contradictory signals for the same command. The `maturity` command now reads the
canonical registry, so the two signals agree command by command. An anti-drift
test (`tests/cli/test_maturity_command_matches_help_policy.py`) fails if the
command ever reads a different table again.

`command_maturity.py` is a **legacy** wider *visibility* map, retained only for
its completeness test (`tests/cli/test_command_maturity_completeness.py`, which
verifies every registered command carries a classification). It is no longer a
user-facing source of truth and is **recommended for eventual removal** once the
completeness assertion is ported onto the canonical registry.
