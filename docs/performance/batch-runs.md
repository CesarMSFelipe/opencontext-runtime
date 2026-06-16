# Batch Runs

## Purpose
Batch planning shares repo map and retrieval across related questions while keeping separate outputs.

## Current Status
Implemented as local deterministic scaffolds; provider-specific cache and cost integrations are future adapters outside core.

## Related Commands
```bash
opencontext cache plan --query "review auth"
opencontext cache warm --workflow code-review
opencontext report cost
opencontext harness run --workflow explore-only --task "security audit"
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/operating_model/performance.py`
