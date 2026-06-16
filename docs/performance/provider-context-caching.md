# Provider Context Caching

## Purpose
ProviderContextCacheAdapter is a provider-neutral scaffold. It does not call provider cache APIs unless policy later enables explicit caching.

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
