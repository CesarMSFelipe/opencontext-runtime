# Python Sdk

## Purpose
Use `OpenContextRuntime` directly for Python integration. Keep provider SDKs outside core.

## Current Status
CLI/API/local SDK paths are implemented. Agent-specific integrations are documented patterns unless a command explicitly exists.

## Related Commands
```bash
opencontext agent-context "Review access control" --target codex --copy
opencontext pack . --query "review auth" --copy
```

## Implemented Code
- `packages/opencontext_cli/opencontext_cli/main.py`
- `packages/opencontext_api/opencontext_api/main.py`
- `packages/opencontext_core/opencontext_core/runtime.py`
