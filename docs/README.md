# OpenContext Documentation

Start with the root [README](../README.md). It explains the product, runtime-first setup,
safe defaults, CLI path, and current implementation status. This docs index is the deeper
navigation layer.

## First Reads

- [Runtime-first setup](getting-started/runtime-first.md)
- [First context pack](getting-started/first-context-pack.md)
- [Zero-key mode](getting-started/zero-key-mode.md)
- [Configuration overview](configuration/overview.md)
- [Architecture overview](architecture/overview.md)
- [Security threat model](security/threat-model.md)

## Product Concepts

- [What is context engineering?](concepts/what-is-context-engineering.md)
- [Architecture](concepts/architecture.md)
- [Context packs](concepts/context-packs.md)
- [Repo maps](concepts/repo-map.md)
- [Token budgets](concepts/token-budgets.md)
- [Memory](concepts/memory.md)
- [Output budgets](concepts/output-budgets.md)
- [Technology profiles](concepts/technology-profiles.md)
- [Controlled agentic harness](concepts/controlled-agentic-harness.md)

## Architecture

- [Overview](architecture/overview.md)
- [Project intelligence layer](architecture/project-intelligence-layer.md)
- [Repo-map engine](architecture/repo-map-engine.md)
- [Context pack builder](architecture/context-pack-builder.md)
- [Context optimization layer](architecture/context-optimization-layer.md)
- [Compression](architecture/compression.md)
- [Safety layer](architecture/safety-layer.md)
- [Cache layer](architecture/cache-layer.md)
- [Workflow engine](architecture/workflow-engine.md)
- [Evaluation layer](architecture/evaluation-layer.md)
- [Observability](architecture/observability.md)
- [Trace model](architecture/trace-model.md)
- [Technology profiles](architecture/technology-profiles.md)
- [Implementation matrix](architecture/implementation-matrix.md)

## Guides

- [Agent hints](guides/agent-hints.md) — Project-specific instructions for AI agents
- [CI checks](guides/ci-checks.md) — Automated code review checks
- [Git context](guides/git-context.md) — Git-aware knowledge graph enrichment
- [Five-minute setup](guides/five-minute-setup.md)
- [Agent orchestration](guides/agent-orchestration.md)

## Runtime Areas

- [Token efficiency](token-efficiency/overview.md)
- [Memory](memory/overview.md)
- [Workflows](workflows/overview.md)
- [Quality](quality/context-quality-evaluation.md)
- [Performance](performance/context-layers.md)
- [Operations](operations/run-receipts.md)

## Configuration

- [Overview](configuration/overview.md)
- [Reference](configuration/reference.md)
- [Defaults](configuration/defaults.md)
- [Security policy](configuration/security-policy.md)
- [Provider policy](configuration/provider-policy.md)
- [Tool policy](configuration/tool-policy.md)
- [Memory policy](configuration/memory-policy.md)
- [Output policy](configuration/output-policy.md)
- [Cache policy](configuration/cache-policy.md)
- [Workflow config](configuration/workflow-config.md)
- [Templates](configuration/templates.md)

## Security

- [Threat model](security/threat-model.md)
- [Secret scanning](security/secret-scanning.md)
- [Redaction and DLP](security/redaction-and-dlp.md)
- [Prompt injection](security/prompt-injection.md)
- [Source trust boundaries](security/source-trust-boundaries.md)
- [Data classification](security/data-classification.md)
- [Provider policies](security/provider-policies.md)
- [Egress policy](security/egress-policy.md)
- [Tool security](security/tool-security.md)
- [MCP and tool security](security/mcp-and-tool-security.md)
- [Cache and memory isolation](security/cache-and-memory-isolation.md)
- [Secure tracing](security/secure-tracing.md)
- [Prompt/context SBOM](security/prompt-context-sbom.md)
- [Release artifact audit](security/release-artifact-audit.md)
- [Air-gapped mode](security/air-gapped-mode.md)

## Integrations

- [Python SDK](integrations/python-sdk.md)
- [API](integrations/api.md)
- [CLI](integrations/cli.md)
- [Codex](integrations/codex.md)
- [Claude Code](integrations/claude-code.md)
- [Cursor](integrations/cursor.md)
- [Windsurf](integrations/windsurf.md)
- [OpenCode and Kilo Code](integrations/opencode-kilo-code.md)
- [GitHub Action](integrations/github-action.md)
- [DDEV](integrations/ddev.md)

## Development

- [Contributing](development/contributing.md)
- [Testing](development/testing.md)
- [Architecture boundaries](development/architecture-boundaries.md)
- [Adding a command](development/adding-a-command.md)
- [Adding a serializer](development/adding-a-serializer.md)
- [Adding a memory backend](development/adding-a-memory-backend.md)
- [Adding a profile](development/adding-a-profile.md)
- [Release checklist](release-checklist.md)
- [Roadmap](ROADMAP.md)
