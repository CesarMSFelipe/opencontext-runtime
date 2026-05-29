# Zero-Key Mode

## Purpose
Show how OpenContext works usefully with no API keys.

## Current Status
The default model provider is `mock/mock-llm`. Indexing, repo maps, token reports, context packs, memory commands, doctor checks, release audit, prompt audit, and many governance scaffolds run locally.

## Commands
```bash
opencontext install
opencontext index .
opencontext knowledge-graph view --format tree
opencontext pack . --query "Explain this project"
opencontext memory init
opencontext security scan .
```

## Safety Notes
Zero-key mode is the recommended first run path. It does not enable external providers, tool execution, network egress, MCP, or raw trace storage.
