# Workflow Packs

## Purpose
Workflow packs live under `workflow-packs/` and remain policy-governed. External packs cannot silently weaken security defaults.

## Current Status
Core `code_assistant` execution is implemented. Local HMAC integrity signing for workflow pack directories is handled internally. Public-key signing, transparency logs, and external trust roots are scaffolded.

## Related Commands
```bash
opencontext workflows list
opencontext harness run --workflow explore-only --task "security audit"
opencontext harness run --workflow sdd --task "review architecture"
opencontext harness run --workflow sdd --task "fix tests"
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/workflow/`
- `packages/opencontext_core/opencontext_core/workflow_packs/signing.py`
- `packages/opencontext_cli/opencontext_cli/main.py`
