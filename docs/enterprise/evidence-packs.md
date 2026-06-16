# Evidence Packs

## Purpose
Evidence packs collect hashes, policy decisions, context pack metadata, run receipts, security scans, release audit findings, and token reports without raw secrets.

## Current Status
Local release evidence is implemented with file hashes and leak-audit findings through `opencontext release evidence`. Broader enterprise evidence packaging, signing, and attestation remain scaffolded. Do not treat the project as a fully certified enterprise platform yet.

## Related Commands
```bash
opencontext report
opencontext release evidence --dist dist/
opencontext prompt sbom --trace last
opencontext org baseline check
opencontext release gate
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/operating_model/`
- `packages/opencontext_core/opencontext_core/operating_model/evidence.py`
- `packages/opencontext_core/opencontext_core/safety/`
