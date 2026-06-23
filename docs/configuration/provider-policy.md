# Provider Policy

## Purpose
Provider policies define allowed classifications, redaction requirements, zero-data-retention requirements, private endpoint requirements, and training opt-in rules.

## Current Status
Config models are implemented in `packages/opencontext_core/opencontext_core/config.py`. Provider adapter contracts live in core at `opencontext_core/providers/adapters.py` (provider-neutral; SDK-free). The mock adapter is implemented for zero-key mode; real external adapters remain application-level scaffolds and must be explicitly enabled by policy.

## Related Commands
```bash
opencontext init --template generic
opencontext init --template enterprise
opencontext doctor security
opencontext provider simulate --provider openai --classification confidential
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/config.py`
- `packages/opencontext_core/opencontext_core/providers/adapters.py`
