# Playbooks

## Purpose
Playbooks live under `.opencontext/playbooks/` and describe repeatable workflows such as review-pr, security-audit, release-gate, generate-tests, and architecture-review.

## Current Status
Local scaffolds are implemented for command registry, hook registry, approvals, playbooks, baselines, run receipts, and reports. They do not execute external actions by default.

## Related Commands
```bash
opencontext playbooks list
opencontext command run review-pr
opencontext approvals list
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/operating_model/team.py`
