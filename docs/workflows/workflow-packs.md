# Workflow Packs

## Purpose
Workflow packs live under `workflow-packs/` and remain policy-governed. External packs cannot silently weaken security defaults.

## Current Status
Workflow execution is implemented by the configurable workflow engine (`workflow/engine.py`), which runs named YAML workflows through an explicit step registry. Local HMAC integrity signing is provided by the marketplace signer (`marketplace/signing.py`); public-key signing, transparency logs, and external trust roots are not yet implemented.

> Note: the standalone `workflow_packs` Python package (including its `signing.py`) was removed in 2.0.0. Workflow-pack *references* on technology profiles are unaffected — they use `WorkflowPackReference` from `opencontext_core.project.profiles`.

## Related Commands
```bash
opencontext workflows list
opencontext harness run --workflow explore-only --task "security audit"
opencontext harness run --workflow sdd --task "review architecture"
opencontext harness run --workflow sdd --task "fix tests"
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/workflow/`
- `packages/opencontext_core/opencontext_core/marketplace/signing.py`
- `packages/opencontext_cli/opencontext_cli/main.py`
