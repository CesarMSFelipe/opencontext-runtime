# Drupal

## Purpose
Drupal profile hints ignore uploaded files and cache directories and focuses on modules, services, routes, config, and access checks.

## Current Status
First-party profile registry exists in `packages/opencontext_profiles`. CLI templates can select profile names.

## Related Commands
```bash
opencontext init --template drupal
opencontext init --template python
opencontext verify
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/project/profiles.py`
- `packages/opencontext_profiles/opencontext_profiles/`
