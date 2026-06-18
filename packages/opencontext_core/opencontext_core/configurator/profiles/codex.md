# OpenContext — Codex Profile

OpenContext gives you a semantic knowledge graph + verified context for this project.

## How Codex uses OpenContext

Codex receives context via the instructions file — MCP tools are not called directly
by Codex. Instead, use the CLI to generate verified context and paste it into Codex.

## Recommended workflow

1. Generate context: `opencontext pack . --query 'your task' --copy`
2. Paste the copied context into Codex as part of your prompt
3. For impact analysis: `opencontext_impact <symbol>` in your terminal first

## CLI tools

- `opencontext pack . --query 'your task' --copy` — get verified context, copy to clipboard
- `opencontext search <symbol>` — find symbols by name
- `opencontext index .` — rebuild the knowledge graph after large changes

## Keep the index fresh

Run `opencontext index .` after large changes to ensure context is up to date.
