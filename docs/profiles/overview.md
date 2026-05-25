# Overview

## Purpose
Profiles keep framework-specific knowledge outside core.

## Current Status
First-party profile registry exists in `packages/opencontext_profiles`. CLI templates can select profile names.

## Related Commands
```bash
opencontext init --template drupal
opencontext init --template python
opencontext init --template node
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/project/profiles.py`
- `packages/opencontext_profiles/opencontext_profiles/`
