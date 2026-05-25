# Quickstart

## Purpose
Create a safe local workspace, index a project, and generate a first context pack without API keys.

## Current Status
Zero-key mode works through the deterministic `mock` provider and local context pack generation. External providers, MCP, native tools, network, and filesystem writes are disabled by default.

## Shortest Path

```bash
pip install opencontext-core opencontext-cli
cd your-project
opencontext install
opencontext pack . --query "Review authentication" --mode plan --copy
```

`opencontext install` works on **Linux, macOS, and Windows** (via PowerShell). It auto-detects
your project stack and configures SDD/TDD, project index, knowledge graph, and agent integrations
in one step. Use `opencontext install --yes` for non-interactive setup.

This is enough for a first run. It creates local harness files, indexes the project, builds a
compact context pack, redacts secrets, records token accounting, and keeps a trace id for audit.

## Commands
```bash
cd your-project
opencontext install
opencontext doctor
opencontext index .
opencontext pack . --query "Review authentication" --mode plan --copy
```

This scans the project, builds a repo map, redacts secrets, selects high-signal context, keeps the pack under budget, and copies or prints it for an AI coding agent.

## Runtime Alternative

```python
from opencontext_core import OpenContextRuntime

runtime = OpenContextRuntime()
runtime.setup_project(".")
prepared = runtime.prepare_context("Review authentication", max_tokens=6000)
print(prepared.context)
```

Use this path for IDEs, services, local wrappers, or any product where users should not need to run
OpenContext commands directly.

## Implemented Code
- Onboarding: `packages/opencontext_cli/opencontext_cli/main.py`
- Indexing: `packages/opencontext_core/opencontext_core/indexing/project_indexer.py`
- Packing: `packages/opencontext_core/opencontext_core/context/packing.py`
