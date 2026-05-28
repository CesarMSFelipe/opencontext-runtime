# Troubleshooting

## Purpose
Help users diagnose setup, config, indexing, and token issues.

## Current Status
`opencontext doctor` reports runtime, security, provider, token, and tool posture. Validation commands are local.

## Commands
```bash
opencontext doctor
opencontext doctor security
opencontext doctor tokens --suggest-ignore
opencontext doctor tools
ruff check .
pytest
```

## Common Fixes
- Missing config: run `opencontext install`.
- Too much context: lower `--max-tokens`, add ignore patterns, or use `--format toon`.
- Unsafe provider: keep `providers.external_enabled: false` unless policy and redaction are configured.
