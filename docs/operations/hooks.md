# Hooks

## Purpose
Hooks are policy-scaffolded pre/post workflow checks such as security.scan, prompt.audit, trace.persist, and tokens.report.

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
