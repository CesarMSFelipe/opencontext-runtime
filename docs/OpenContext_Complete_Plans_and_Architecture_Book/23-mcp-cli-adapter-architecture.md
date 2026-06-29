# OpenContext MCP, CLI & Adapter Architecture
## Version 1.0 (Draft)
### Document ID
OC-INTERFACES-001

# Purpose

This document defines how OpenContext is exposed through MCP, CLI, TUI, IDE adapters and future agent surfaces.

Interfaces are presentation and integration layers.

They must not own runtime logic.

# Mission

OpenContext interfaces exist to make the Runtime usable from:

- MCP clients
- CLI
- TUI
- Studio
- IDEs
- external agent runtimes
- CI systems
- plugin tools

Every interface must call the same Runtime API and consume the same public contracts.

# Core Principles

1. Interfaces never bypass Runtime.
2. Interfaces do not mutate files directly.
3. Interfaces do not write memory directly.
4. Interfaces do not execute workflows directly.
5. Interfaces render public contracts.
6. MCP and CLI should expose equivalent capabilities.
7. UX differs by surface; semantics do not.
8. All interface actions are observable.
9. Every external request produces events/receipts when meaningful.
10. Headless operation must remain first-class.

# Interface Layer

```text
MCP Server
CLI
TUI
IDE Adapters
CI Adapter
Studio
External Agent Adapters
        ↓
Runtime API
```

# Runtime API Boundary

All interfaces call:

```python
RuntimeApi.start_session()
RuntimeApi.run()
RuntimeApi.next()
RuntimeApi.observe()
RuntimeApi.apply()
RuntimeApi.inspect()
RuntimeApi.resume()
RuntimeApi.archive()
RuntimeApi.status()
```

No interface should instantiate:

- HarnessRunner
- WorkflowRunner
- phases
- personas
- skills
- harnesses
- providers

directly.

# MCP Architecture

The MCP server is the primary agent integration surface.

Required MCP tools:

- opencontext_run
- opencontext_session_start
- opencontext_session_next
- opencontext_session_observe
- opencontext_session_apply
- opencontext_session_inspect
- opencontext_session_status
- opencontext_session_resume
- opencontext_session_archive
- opencontext_workflow_list
- opencontext_workflow_explain
- opencontext_profile_list
- opencontext_profile_explain
- opencontext_doctor
- opencontext_context
- opencontext_search
- opencontext_node
- opencontext_impact
- opencontext_quality

# MCP Tool Contract

Each MCP tool must define:

- input schema
- output schema
- capability requirements
- policy behaviour
- error codes
- artifact references
- user-facing summary

# opencontext_run

`opencontext_run` is the high-level compatibility tool.

It must support:

```json
{
  "task": "...",
  "workflow": "auto|sdd|oc-flow|quick|standard",
  "profile": "balanced",
  "mode": "run_to_completion|interactive|dry_run|simulate"
}
```

It returns:

```json
{
  "session_id": "...",
  "run_id": "...",
  "workflow": "oc-flow",
  "status": "completed",
  "summary": "...",
  "artifacts": {},
  "receipts": {},
  "gates": {},
  "cost": {},
  "confidence": {},
  "next_recommended": "..."
}
```

# Session MCP Tools

Session tools support advanced orchestration by external agents.

They allow step-by-step execution without losing Runtime governance.

No session tool may bypass policies.

# CLI Architecture

CLI is the primary human/headless surface.

Required commands:

```bash
opencontext init
opencontext doctor
opencontext index
opencontext run "task"
opencontext simulate "task"
opencontext workflow list
opencontext workflow explain sdd
opencontext profile list
opencontext profile explain balanced
opencontext session list
opencontext session status <id>
opencontext session resume <id>
opencontext session archive <id>
opencontext benchmark
opencontext health
opencontext studio
```

# CLI Output Modes

Supported output modes:

- human
- json
- yaml
- quiet
- verbose

Human output should be concise.

JSON/YAML output should expose full public contracts.

# TUI Architecture

The TUI is a terminal visualization layer.

It consumes:

- live-state.json
- events.jsonl
- artifacts
- receipts
- cost/confidence reports

It does not execute runtime logic directly.

# IDE Adapters

IDE adapters should support:

- run task
- show current session
- show patch
- show receipts
- show context used
- approve policy requests
- resume session

They must call Runtime API or MCP tools.

# CI Adapter

CI usage should be non-interactive by default.

Required behaviour:

- no approval prompts unless explicitly configured;
- fail safely on policy ask/deny;
- emit machine-readable reports;
- store artifacts.

# External Agent Adapters

Adapters for Claude Code, Codex, OpenCode, Cursor, Windsurf and similar tools should be generated from public contracts where possible.

No agent adapter should define separate runtime semantics.

# Error Handling

Interface errors must be actionable.

Every interface error should include:

- error code
- message
- recoverability
- next action
- artifact path if available

# Streaming

Interfaces may stream:

- events
- live state
- node progress
- tool output summaries

Streaming is optional but recommended for long-running workflows.

# Security

Interfaces must respect:

- policy decisions
- approvals
- redaction
- plugin permissions
- provider restrictions

No interface should expose secrets.

# Observability

Every interface call should emit:

- interface.request.started
- interface.request.completed
- interface.request.failed

Meaningful calls should create receipts.

# Configuration

```yaml
interfaces:
  mcp:
    enabled: true
    expose_session_tools: true

  cli:
    default_output: human

  tui:
    enabled: true

  ide:
    enabled: false

  ci:
    non_interactive: true
```

# Migration from Current Branch

The current MCP server should migrate incrementally:

1. Preserve existing MCP tools.
2. Route `opencontext_run` through Runtime API.
3. Add session tools.
4. Add workflow/profile explain tools.
5. Improve output schemas.
6. Return artifact/receipt paths.
7. Add doctor/status tools.

# Invariants

1. Interfaces call Runtime API.
2. Interfaces do not mutate directly.
3. Interfaces do not own workflow logic.
4. MCP and CLI share public contracts.
5. Interface output is evidence-backed.
6. Headless operation remains supported.
7. Errors are actionable.
8. Sensitive data is redacted.

# Definition of Done

Implemented when:

- MCP tools use Runtime API.
- CLI uses Runtime API.
- Session tools exist.
- run output includes artifacts/receipts/cost/confidence.
- doctor works.
- simulate works.
- workflow/profile explain works.
- CI mode works.
- interface events are emitted.

# Final Statement

Interfaces are the doors into OpenContext.

They should make the Runtime easy to use without weakening its governance.
