# Custom Workflows

## Purpose
Custom workflows are scaffolded as named steps in YAML. Execution adapters must remain thin and call core policy gates.

## Current Status
Core `code_assistant` execution is implemented. Many team workflow commands are honest scaffolds that print policy and token plans without provider/tool calls.

## Related Commands
```bash
opencontext workflows list
opencontext harness run --workflow explore-only --task "security audit"
opencontext harness run --workflow sdd --task "review architecture"
opencontext harness run --workflow sdd --task "fix tests"
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/workflow/`
- `packages/opencontext_cli/opencontext_cli/main.py`
