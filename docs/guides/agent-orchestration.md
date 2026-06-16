# Agent and Orchestration Integration Guide

This guide explains how to run OpenContext Runtime as a context engine for
modern coding-agent stacks (for example Codex-style agents, Claude Code-style
agents, and similar "open code" orchestrators).

## Scope and guarantees

OpenContext Runtime is not an agent framework. It is a secure context runtime
that can be used by agent frameworks as a deterministic context provider and a
permissioned planning harness. Scaffolded action surfaces report allow/ask/deny
decisions, but do not execute shell commands, write files, use network tools, or
enable MCP by default.

## Recommended integration pattern

1. Agent receives user task.
2. Agent calls OpenContext API `POST /v1/runs` or CLI `opencontext ask "..."`
   to execute a configured workflow.
3. OpenContext performs:
   - project retrieval,
   - token budgeting,
   - ranking and packing,
   - prompt assembly with untrusted-context wrapping,
   - provider policy checks before generation,
   - sanitized trace persistence.
4. Agent consumes response and trace metadata.

## Security mode recommendations

- **developer**: local experiments only.
- **private_project**: recommended default.
- **enterprise**: strict mode for managed environments.
- **air_gapped**: local/provider-restricted environments only.

For agent orchestration in enterprise settings:

- keep `external_providers_enabled: false` by default,
- explicitly allow providers with classification-aware policy,
- keep MCP disabled unless an explicit threat model and allowlist exist,
- require sanitized traces for audit review.

## Interoperability notes

OpenContext integrates at the protocol boundary (CLI/API), so it can be used
with any orchestrator that can invoke shell commands or HTTP endpoints:

- Codex-like local coding agents,
- Claude Code-like terminal agents,
- Open-source orchestrators with workflow runners.

No provider SDK is required in `opencontext_core`; provider adapters remain a
gateway concern.

## Minimal runbook

```bash
opencontext init
opencontext index .
opencontext ask "Where is access control implemented?"
opencontext harness run --workflow sdd --task "Fix access resolver tests"
opencontext verify
opencontext trace last
```

Or via API:

```bash
curl -X POST http://127.0.0.1:8000/v1/index -H "content-type: application/json" -d '{"root":"."}'
curl -X POST http://127.0.0.1:8000/v1/runs -H "content-type: application/json" -d '{"input":"Where is access control implemented?"}'
curl -X POST http://127.0.0.1:8000/v1/orchestrate -H "content-type: application/json" -d '{"requirements_path":"requirements.md"}'
```
