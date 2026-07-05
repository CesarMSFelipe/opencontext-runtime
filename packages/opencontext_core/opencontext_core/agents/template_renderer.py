"""Consolidated agent instructions template renderer.

The renderer is the single source of truth for the managed markdown block
written into each agent's instructions file (AGENTS.md / CLAUDE.md / GEMINI.md
/ QWEN.md). It replaces the inline ``_default_instructions`` in
``configurator.service`` so the content can be unit-tested and so any future
schema change is localised to one module.

Design rules (AHE-008):

- Topic coverage MUST be driven by the live MCP tool registry (or, when a
  tool is not present in the registry, by a documented "topic" entry). Hard
  coding tool counts is explicitly disallowed by the spec.
- TDD is presented as a mode/gate inside OC Flow and SDD, never as a
  standalone workflow.
- The ``--scope=local`` decision is fixed: Host-Constrained Local. Project
  instructions are written locally; global MCP/persona files may be written
  for hosts that only support global MCP config, and every such write is
  reported in the setup JSON via ``global_write_reason``.
- Engram is documented as an opt-in backend, not the default. The default
  memory mode is OpenContext-only (runtime-backed MCP, local store).
- No stale OpenCode slash-command claims (``/context``, ``/impact``,
  ``/search``) — OpenCode does not install those command files.
"""

from __future__ import annotations

from collections.abc import Callable

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# Spec 8.9: --scope local is Host-Constrained Local. Project instructions stay
# local; global MCP/persona files may be written for hosts that only support
# global MCP config, with every such write reported under
# global_files_written + global_write_reason.
HOST_CONSTRAINED_LOCAL_REASON: str = "Host-Constrained Local"

# Spec 8.9: the JSON output's global_write_reason for the host-constrained
# branch. Single source of truth — used by the configurator and asserted by
# tests so the wording can never silently drift.
RENDER_SCOPE_LOCAL_REASON: str = (
    "Host-constrained local setup: this agent stores MCP/persona config under "
    "its home config directory."
)


# --------------------------------------------------------------------------- #
# Topic registry — single source of truth for the doc body
# --------------------------------------------------------------------------- #

# Each topic is (heading, body). ``body`` is plain markdown. Topics are
# referenced by name from the topic-coverage tests so a missing topic fails
# the spec at the unit level rather than at review time.

_KG_READ_TOOLS: tuple[tuple[str, str], ...] = (
    ("opencontext_search", "Find symbols by name"),
    ("opencontext_context", "Build relevant code context for a task"),
    ("opencontext_callers", "Trace call flow (who calls a function)"),
    ("opencontext_callees", "Trace call flow (what a function calls)"),
    ("opencontext_impact", "Check what's affected before editing"),
    ("opencontext_node", "Get a single symbol's details"),
    ("opencontext_files", "Get indexed file structure"),
)

_KG_STATUS_TOOLS: tuple[tuple[str, str], ...] = (
    ("opencontext_status", "Check index health"),
    ("opencontext_trace", "Trace a call chain through the graph"),
    ("opencontext_doctor", "Run config + health checks (config doctor)"),
)

_RUN_QUALITY_SESSION_TOOLS: tuple[tuple[str, str], ...] = (
    ("opencontext_run", "Run an OC Flow or SDD workflow from the agent"),
    ("opencontext_quality", "Inspect a code change for regressions"),
    ("opencontext_session_start", "Start a multi-step session"),
    ("opencontext_session_next", "Advance a session to the next node"),
    ("opencontext_session_observe", "Observe the current session state"),
    ("opencontext_session_apply", "Apply a session step"),
    ("opencontext_session_inspect", "Inspect a session's run/event history"),
    ("opencontext_session_status", "Read a session's status"),
    ("opencontext_session_resume", "Resume a paused session"),
    ("opencontext_session_archive", "Archive a finished session"),
)

_WORKFLOW_PROFILE_TOOLS: tuple[tuple[str, str], ...] = (
    ("opencontext_workflow_list", "List available workflows"),
    ("opencontext_workflow_explain", "Explain when to use a workflow and its cost"),
    ("opencontext_profile_list", "List config/model profiles"),
    ("opencontext_profile_explain", "Explain a profile (family, security, approvals)"),
)

_SYMBOL_EDIT_TOOLS: tuple[tuple[str, str], ...] = (
    ("opencontext_replace_symbol_body", "Replace a function/class body"),
    ("opencontext_insert_before_symbol", "Insert code before a symbol"),
    ("opencontext_insert_after_symbol", "Insert code after a symbol"),
    ("opencontext_rename_symbol", "Rename a symbol across the codebase"),
)


def _tool_table(rows: tuple[tuple[str, str], ...]) -> str:
    """Format a (tool, use_for) tuple as a markdown table."""
    if not rows:
        return ""
    lines = ["| Tool | Use For |", "|------|---------|"]
    lines.extend(f"| `{name}` | {desc} |" for name, desc in rows)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Topic sections
# --------------------------------------------------------------------------- #

_INTRO_SECTION = """# OpenContext Integration

OpenContext provides a semantic knowledge graph, health checks, plugin
ecosystem, and SDD orchestration for this project. Use the MCP tools directly
rather than re-reading files you can query.

"""


_KG_SECTION = """## Knowledge Graph (MCP Tools)

OpenContext indexes your project into a queryable knowledge graph with call
analysis. The number of tools and their exact surface are taken from the live
MCP registry — run `opencontext_status` or your host's tool catalog to see the
current shape.

### Read tools — always safe to call

{read_table}

### Status and health

{status_table}

### Rules

1. Use `opencontext_context` for exploration questions.
2. Do NOT re-read files that `opencontext_context` already returned.
3. Check `opencontext_impact` before making changes.
4. Run `opencontext_doctor` if something seems wrong.
"""


_RUN_QUALITY_SECTION = """## Workflows, Quality, and Sessions

### Run, quality, and session tools

{run_table}

### Workflow and profile explain

{workflow_table}

### When to use what

- `opencontext_run` is the right entry point for a one-shot, scoped change.
- `opencontext_session_start` + `opencontext_session_next` is for multi-step
  work you want to resume later.
- `opencontext_quality` is the read-side companion to any change you are
  about to apply — call it on a diff or file list before you ship.
- `opencontext_workflow_explain` and `opencontext_profile_explain` answer
  "which workflow fits this task" and "what does this profile gate"
  respectively — call them when the choice is not obvious.

### How `opencontext_run` executes (depends on your host)

- If your host advertises the MCP **sampling** capability at initialize,
  `opencontext_run` executes the workflow directly with YOUR selected model.
  Zero provider config. OpenContext detects this per session, so the path
  engages automatically on any host that advertises it.
- If your host does NOT advertise sampling (none of the known clients do
  today) and no provider is configured in `opencontext.yaml`, a mutation run
  returns `status: "agent_execute"` instead of executing: it carries the task
  contract, a bounded context summary, ordered instructions, and the exact
  follow-up call. Do the edits yourself, then call
  `opencontext_session_apply` with `kind="agent_edits"` and
  `payload.changed_files` (plus `payload.test_command` when a test proves the
  change) so OpenContext verifies the edits, records receipts, and completes
  the run. Re-call it after fixing anything it reports.
"""


_SYMBOL_EDIT_SECTION = """## Symbol-level Edit Tools

Prefer these over raw file edits when the change targets a known symbol —
they survive refactors, leave a receipt, and route through the same policy
gate as any other mutation.

{edit_table}

These tools honour the same approval policy as the rest of the agent. If
approval is required, the result surfaces `approval_required` with a `hint`.
"""


_CLI_REFERENCE_SECTION = """## OpenContext CLI (read-side)

Run `opencontext --help` or `opencontext <command> --help` for the full
command set. Most-used:

- `opencontext index .` — rebuild the knowledge graph.
- `opencontext pack . --query "<task>"` — get verified context for a task.
- `opencontext verify` — health check.
- `opencontext setup` — configure the host agent (use `--scope local`).
- `opencontext doctor` — diagnose config drift.
"""


_HEALTH_SECTION = """## Health & Maintenance

- Run `opencontext verify` to check all components are working.
- Run `opencontext update` to check for OpenContext updates.
- Run `opencontext upgrade` to install the latest version.
- Run `opencontext plugin update` to update all plugins.
- Run `opencontext config backup` before risky configuration changes.
"""


# Spec 8.6: OC Flow vs SDD decision guidance.
_OC_FLOW_VS_SDD_SECTION = """## OC Flow vs SDD — when to use which

- Use **OC Flow** for a one-shot, agent-driven task: explore, mutate, verify.
  It is the path `opencontext_run(workflow="oc-flow")` and the path the
  agent's tool-driven workflow falls into by default.
- Use **SDD** when the work needs a tracked change: explore → propose → spec
  → design → tasks → apply → verify → archive. SDD requires explicit artifacts
  at every phase; the orchestrator (if installed) drives it.
- If you are unsure, call `opencontext_workflow_explain` on the candidate
  workflow and follow the `when` clause. If neither is a fit, fall back to
  `opencontext_context` + targeted edits — the agent's own judgement stays the
  last word.
"""


# Spec 8.7: TDD is a mode/gate, not a standalone workflow.
_TDD_MODE_SECTION = """## TDD — a mode, not a workflow

TDD in OpenContext is a **mode** that gates mutations, not a separate
workflow. The values are `off`, `ask`, and `strict`:

- `off` — TDD is not enforced; agents may mutate without a failing test.
- `ask` — agents are prompted per change; in non-interactive runs this fails
  closed (no silent apply).
- `strict` — every mutation needs failing/new test evidence before apply.

To pick a mode for this project, run `opencontext setup` (or set
`sdd.tdd_mode` in `opencontext.yaml`). The mode is the same gate for both OC
Flow mutations and SDD apply.
"""


# Spec 8.8: memory/Engram guidance — runtime-backed by default, Engram opt-in.
_MEMORY_PROTOCOL_SECTION = """## Memory

OpenContext gives you first-class access to its own memory store via four MCP
tools. Use them WITHOUT being asked, the moment something is worth remembering.

| Tool | Use for |
|------|---------|
| `opencontext_memory_save` | Save a decision, bug, convention, or discovery |
| `opencontext_memory_search` | Recall past records matching a query |
| `opencontext_memory_context` | Pull recent/relevant memory as task context |
| `opencontext_memory_judge` | Reinforce or contradict an existing record |

Save proactively — after any decision, bug fix, convention, or discovery,
call `opencontext_memory_save`. Layers:

- **FAILURE** — bugs, root causes, what went wrong.
- **SEMANTIC** — durable facts and stable knowledge.
- **PROCEDURAL** — repeatable patterns and how-to procedures.
- **EPISODIC** — the default for everything else (omit `layer` to use it).

### Availability

Memory tools are advertised by the catalog, but they only persist when the
runtime-backed MCP server is running. `opencontext_status` exposes a
`memory.available` field — check it before relying on a save. If the field is
`false`, the server will return an `available=false` envelope rather than
silently dropping the write.

### Backend — OpenContext-only is the default; Engram is opt-in

By default, the memory store is local (SQLite under the runtime's storage
path). The OpenContext + Engram opt-in mode routes the SEMANTIC and EPISODIC
layers to a configured Engram server while the other five layers stay local.
Engram is **opt-in** — turning it on is a configuration choice, not the
default. If Engram is configured but unreachable, those layers transparently
fall back to local; the save envelope surfaces `degraded: true` so the
agent knows the record did not reach Engram.
"""


# Spec 8.6 + 8.9: scope semantics.
_SETUP_SCOPE_SECTION = """## Setup — what `opencontext setup` does

`opencontext setup <agent>` configures the host agent to use OpenContext
(MCP server entry + managed instructions block + any agent-specific extras).
The `--scope` flag controls **where instructions land**, not where MCP
config lands:

- `--scope local` (default) — project instructions are local
  (`./AGENTS.md`, `./.mcp.json`, etc.). For hosts that only support
  home-scoped MCP config (OpenCode, Cursor, …), the setup run may also
  write `~/.config/<host>/...` files. This is the **Host-Constrained
  Local** mode: the local intent is preserved, but global writes are
  explicitly reported.

- `--scope global` — every file lands in the host's home config dir.

- `--dry-run` — return the same per-file plan the real run would execute,
  but write nothing. The dry-run plan matches the real run's file set.

Every setup run reports a JSON shape with `local_files_written`,
`global_files_written`, and (when `--scope local` wrote any global file) a
`global_write_reason` explaining the host-constrained decision. The
`--scope=local` decision is fixed for this product: Host-Constrained Local.
"""


_SDD_SECTION = """## SDD Workflow (tracked changes)

This project supports Spec-Driven Development. SDD is the right path for
work that needs a tracked change with artifacts at every phase.

- The orchestrator runs: explore → propose → spec → design → tasks → apply
  → verify → archive.
- To start a change, use the agent-native slash command (e.g. `/oc-new`) or
  call the OC Flow / SDD tool surface via MCP. The project bootstrap wizard
  (`opencontext init`) creates `opencontext.yaml`; it is **not** the SDD
  entrypoint.
- Phase output is validated before completion — junk or scaffold-only
  artifacts are blocked.
"""


_SECURITY_SECTION = """## Security

- All tool executions require approval by default.
- External providers are disabled in secure mode.
- Context redaction is applied automatically.
"""


# --------------------------------------------------------------------------- #
# Renderer entry point
# --------------------------------------------------------------------------- #

# Public — let tests introspect the section set so a future addition is hard
# to forget.
SECTIONS: tuple[tuple[str, str], ...] = (
    ("intro", _INTRO_SECTION),
    ("kg", _KG_SECTION),
    ("run_quality", _RUN_QUALITY_SECTION),
    ("symbol_edit", _SYMBOL_EDIT_SECTION),
    ("cli_reference", _CLI_REFERENCE_SECTION),
    ("health", _HEALTH_SECTION),
    ("oc_flow_vs_sdd", _OC_FLOW_VS_SDD_SECTION),
    ("tdd_mode", _TDD_MODE_SECTION),
    ("memory", _MEMORY_PROTOCOL_SECTION),
    ("setup_scope", _SETUP_SCOPE_SECTION),
    ("sdd", _SDD_SECTION),
    ("security", _SECURITY_SECTION),
)


def _interpolate(body: str, **subs: str) -> str:
    """Format ``body`` substituting named placeholders. Pure function."""
    return body.format(**subs)


def render_agent_instructions(
    agent_id: str,
    *,
    topic_filter: Callable[[str], bool] | None = None,
) -> str:
    """Render the managed instructions body for ``agent_id``.

    ``agent_id`` is kept in the signature so a future per-agent override
    (e.g. an OpenCode-specific tweak) has a stable place to slot in. Today
    every supported agent gets the same body — the per-agent differentiation
    is the surrounding ``Configurator`` behaviour (MCP shape, file paths),
    not the prose.

    ``topic_filter`` lets tests introspect a single section without forcing
    the whole body through assertions. The default is to emit all sections.
    """
    keep = topic_filter or (lambda _name: True)

    parts: list[str] = []
    if keep("intro"):
        parts.append(_INTRO_SECTION.rstrip())
    if keep("kg"):
        parts.append(
            _interpolate(
                _KG_SECTION,
                read_table=_tool_table(_KG_READ_TOOLS),
                status_table=_tool_table(_KG_STATUS_TOOLS),
            ).rstrip()
        )
    if keep("run_quality"):
        parts.append(
            _interpolate(
                _RUN_QUALITY_SECTION,
                run_table=_tool_table(_RUN_QUALITY_SESSION_TOOLS),
                workflow_table=_tool_table(_WORKFLOW_PROFILE_TOOLS),
            ).rstrip()
        )
    if keep("symbol_edit"):
        parts.append(
            _interpolate(
                _SYMBOL_EDIT_SECTION,
                edit_table=_tool_table(_SYMBOL_EDIT_TOOLS),
            ).rstrip()
        )
    if keep("cli_reference"):
        parts.append(_CLI_REFERENCE_SECTION.rstrip())
    if keep("health"):
        parts.append(_HEALTH_SECTION.rstrip())
    if keep("oc_flow_vs_sdd"):
        parts.append(_OC_FLOW_VS_SDD_SECTION.rstrip())
    if keep("tdd_mode"):
        parts.append(_TDD_MODE_SECTION.rstrip())
    if keep("memory"):
        parts.append(_MEMORY_PROTOCOL_SECTION.rstrip())
    if keep("setup_scope"):
        parts.append(_SETUP_SCOPE_SECTION.rstrip())
    if keep("sdd"):
        parts.append(_SDD_SECTION.rstrip())
    if keep("security"):
        parts.append(_SECURITY_SECTION.rstrip())

    return "\n\n".join(parts) + "\n"


__all__ = [
    "HOST_CONSTRAINED_LOCAL_REASON",
    "RENDER_SCOPE_LOCAL_REASON",
    "SECTIONS",
    "render_agent_instructions",
]
