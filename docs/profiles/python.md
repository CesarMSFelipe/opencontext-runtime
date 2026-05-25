# Python

## Purpose
Python profile hints ignore venv, caches, and build artifacts and focuses on modules, tests, typing, and packaging.

## Current Status
First-party profile registry exists in `packages/opencontext_profiles`. CLI templates can select profile names.

## Related Commands
```bash
opencontext init --template python
opencontext init --template python
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/project/profiles.py`
- `packages/opencontext_profiles/opencontext_profiles/`
