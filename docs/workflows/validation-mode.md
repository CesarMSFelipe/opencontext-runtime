# Validation Mode

## Purpose
Validation mode reports planned checks for security, context leakage, token budget, and architecture. Real external execution remains future work.

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
