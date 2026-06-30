# Runtime-First Setup

OpenContext can be embedded without asking users to run OpenContext commands. This is the
recommended first step for agent products, IDE integrations, hosted services, and local wrappers.

The intent is simple: after installation, the host application can create the project harness,
index the repository, prepare safe context, and persist traces through stable Python or HTTP
interfaces. The CLI remains available, but it is not part of the required user workflow.

## Install The Runtime Surface

Install only the packages your integration needs:

```bash
pip install opencontext-core opencontext-api opencontext-profiles
```

The CLI is optional. Add `opencontext-cli` only when users should run explicit terminal commands.

## What Gets Installed

The runtime surface gives a host application:

- Project indexing and manifest persistence.
- Repo map, retrieval, ranking, token packing, and context compression.
- Secret redaction, provider policy checks, prompt injection boundaries, and output guards.
- Local trace persistence with selected and omitted context decisions.
- Project-local harness files under `.opencontext/` for policies, templates, agent guidance,
  model routing, memory placeholders, reports, and eval placeholders.

No provider SDK, vector database, LangChain, LlamaIndex, CLI framework, or network service is
required by `opencontext-core`.

## Bootstrap A Project Without CLI

Use the core facade from your host application:

```python
from opencontext_core import OpenContextRuntime

runtime = OpenContextRuntime()
setup = runtime.setup_project(".")
prepared = runtime.prepare_context("Review authentication", max_tokens=6000)
trace = runtime.load_trace(prepared.trace_id)
```

`setup_project()` creates:

- `.opencontext/` harness directories for policies, templates, agents, models, memory, reports, and evals.
- `opencontext.yaml` when missing.
- A persisted project manifest under the runtime storage path.

The returned `ProjectSetupResult` includes `root`, `config_path`, `workspace_path`,
`manifest_path`, indexed file count, symbol count, and detected technology profiles.

`prepare_context()` creates:

- A redacted context bundle.
- Included and omitted source lists.
- Token accounting.
- A persisted trace retrievable by `trace_id`.

The returned `PreparedContext` is intentionally small enough to pass to an agent or model without
dumping the whole repository.

## Whole-Repo Index, Minimal Model Context

OpenContext indexes the whole non-ignored project so retrieval has repo-wide awareness. It does not
send the whole repository to a model. Each task gets a ranked, packed, redacted subset with source
references, token accounting, and omission reasons.

Use `.opencontextignore` and `.gitignore` to exclude directories that should never be indexed,
such as generated artifacts, vendored dependencies, virtualenvs, logs, and private exports.

## Recommended Host Flow

1. On project open or first agent use, call `runtime.setup_project(root)`.
2. For each user task, call `runtime.prepare_context(task, max_tokens=...)`.
3. Pass `prepared.context` and `prepared.included_sources` to the model as untrusted evidence.
4. Store or display `prepared.trace_id` so the run can be audited later.
5. Load `runtime.load_trace(trace_id)` for trace review, source auditing, token accounting, or
   memory harvesting workflows.

Avoid bypassing the runtime by reading broad file trees directly into prompts. Doing that skips
redaction, ranking, budget enforcement, omission records, and trace persistence.

## Agent Surfaces

Different agent tools use different instruction-file conventions, but the OpenContext flow is the
same:

| Tool | Instruction location | Notes |
| --- | --- | --- |
| Codex | `AGENTS.md` | Use OpenContext context as task evidence; preserve trace ids. |
| Claude Code | `CLAUDE.md` | Keep instructions concise and avoid full-repo dumps. |
| OpenCode | `AGENTS.md` | Uses project instructions plus configured MCP/persona files. |
| Cursor | `.cursor/rules/opencontext.mdc` | Use an always-applied rule. |
| Windsurf | `.windsurf/rules/opencontext.md` | Use workspace-scoped rules. |
| Custom agent | Host-defined | Call `setup_project()` once and `prepare_context()` per task. |

The CLI can generate these files with `opencontext agent init --target <target>`, but runtime/API
integrations can ship equivalent instructions directly.

## HTTP API Surface

Use these endpoints for non-Python integrations:

```http
POST /v1/setup
POST /v1/context
GET /v1/traces/{trace_id}
```

`POST /v1/setup` prepares the harness and index. `POST /v1/context` retrieves, packs, redacts,
and persists task-specific context.

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

The context response includes `trace_id`, `context`, `included_sources`, `omitted_sources`, and
`token_usage`.

## Safety Defaults

The runtime-first path keeps the same defaults as the CLI:

- External providers disabled.
- Tools and MCP disabled.
- Raw traces disabled.
- Secrets redacted before context export and trace persistence.
- Omission reasons and token usage recorded for audit.

## What To Commit

For open source projects, commit source code, reusable docs, tests, configs, and examples. Do not
commit local runtime state such as `.opencontext/`, `.storage/`, `.agents/`, virtualenvs, caches,
trace files, or generated analysis reports. The project `.gitignore` excludes these by default.

Reusable documentation belongs under `docs/`. Project-local generated harness files are recreated
by `setup_project()`.
