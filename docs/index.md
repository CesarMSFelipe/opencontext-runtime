---
title: OpenContext Runtime
description: Context engineering runtime for AI coding agents.
hide:
  - navigation
  - feedback
  - toc
---

# OpenContext Runtime

Context engineering runtime for AI coding agents. Index your project into a queryable knowledge graph. Retrieves relevant, ranked, redacted context for each task.

## Quick Start

```bash
pip install opencontext-cli
cd your-project
opencontext setup --preset context-first
```

```bash
opencontext pack . --query "How does auth work?" --copy
```

## Setup Presets

| Preset | Description | Agents |
|--------|-------------|--------|
| `context-first` | KG + retrieval + git. No agents. Offline. | No |
| `context-essential` | Just the basics — KG and git integration. | No |
| `full` | KG, learning, governance, MCP, plugins. | Yes |
| `enterprise` | Governance, audit, team policies. | No |
| `air-gapped` | Completely offline. | No |

## Features

- **Knowledge Graph** — Indexes symbols, call chains, imports, framework routes into SQLite. No external services.
- **Context Packs** — Retrieves relevant code for a task. Token-budgeted, ranked, redacted.
- **MCP Tools** — 32 tools for search, context, graph tracing, impact analysis, symbol edits, memory, quality, session steps, and in-process agentic runs.
- **SDD Workflow** — Spec-Driven Development with phase governance and traceable decisions.
- **Agent Memory** — 5-layer local memory (SQLite + FTS5). Past outcomes, learned rules, failure patterns.
- **Security** — Secrets redacted, external providers disabled by default, air-gapped mode supported.

## Documentation

- [Installation](getting-started/installation.md)
- [Quickstart](getting-started/quickstart.md)
- [Configuration Reference](configuration/reference.md)
