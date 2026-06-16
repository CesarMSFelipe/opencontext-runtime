# Approvals

## Purpose
Approvals are workflow nodes for provider use, tool calls, egress, file writes, memory storage, release exceptions, and policy changes.

## Current Status
Implemented locally as a JSON-backed inbox under `.opencontext/approvals`. Approval requests can be listed, approved, and denied. Enforcement across future provider/tool execution remains scaffolded and fail-closed.

## Related Commands
```bash
opencontext approvals list
opencontext approvals request --kind provider_use --reason "Use approved private endpoint"
opencontext approvals approve <approval_id>
opencontext approvals deny <approval_id>
```

## Implemented Code
- `packages/opencontext_core/opencontext_core/operating_model/team.py`
- `packages/opencontext_cli/opencontext_cli/main.py`
