# DDEV

## Status

The dedicated DDEV integration command has been removed. Use OpenContext's
standard CLI inside a DDEV web container the same way you would in any shell.

## Related Commands
```bash
opencontext agent-context "Review access control" --target codex --copy
opencontext pack . --query "review auth" --copy
```

## Implemented Code
- `packages/opencontext_cli/opencontext_cli/main.py`
- `packages/opencontext_api/opencontext_api/main.py`
- `packages/opencontext_core/opencontext_core/runtime.py`
