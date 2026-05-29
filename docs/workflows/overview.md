# Overview

## Purpose
Workflows compile context, policy, provider, tool, memory, cache, quality, and trace decisions into repeatable runs.

## Current Status
Core `code_assistant` execution is implemented. SDD-style workflow steps are implemented as safe
context proposal, apply, test, verify, review, archive, and trace-persist phases. Many team workflow
commands are honest scaffolds that print policy and token plans without provider/tool calls.

The controlled harness planner is implemented as a preflight model for agentic turns. It models
preprocessing, LLM streaming, error recovery, tool execution, and continuation checks without
executing native tools by default.

## Workflow Boundaries

- Workflow steps call core services and mutate `WorkflowRunState`.
- Provider calls go through the provider-neutral LLM gateway abstraction.
- Native tool execution remains disabled unless an explicit registry and permission policy allow it.
- Tool call plans are evaluated by read/write/network capabilities, approval requirements, and
  execution mode.
- Traces persist workflow step durations, selected context, omitted context, token budgets, prompt
  sections, and safety metadata.

## Related Commands
```bash
opencontext harness list
opencontext harness run --workflow sdd --task "review architecture"
opencontext workflow resume <run-id>
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/workflow/`
- `packages/opencontext_cli/opencontext_cli/main.py`
