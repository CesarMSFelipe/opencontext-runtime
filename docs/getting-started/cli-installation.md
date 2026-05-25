# CLI Installation

The CLI is a convenience adapter, not the required runtime path. Install it when a user or team
wants explicit `opencontext` commands for local diagnosis, context packs, memory operations, or
release checks.

## From PyPI (After Publishing)

```bash
pip install opencontext-cli
```

This also installs `opencontext-core` and `opencontext-profiles` as dependencies.

## From Source (Current Development)

```bash
git clone https://github.com/CesarMSFelipe/OpenContext-Runtime.git
cd OpenContext-Runtime
pip install -e packages/opencontext_cli
```

## Typical Usage

```bash
opencontext install             # Auto-detect & configure project (cross-platform)
opencontext index .             # Index project code
opencontext pack . --query "Review authentication" --mode plan --copy
```

## Command Mapping

The CLI commands map directly to runtime-first APIs:

| CLI command | Runtime/API equivalent |
| --- | --- |
| `opencontext onboard` | `runtime.setup_project(...)` or `POST /v1/setup` |
| `opencontext index .` | `runtime.index_project(...)` |
| `opencontext pack . --query ...` | `runtime.prepare_context(...)` or `POST /v1/context` |
| `opencontext trace last` | `runtime.latest_trace()` |

## When to Use the CLI

Use the CLI for:

- Manual onboarding and doctor checks.
- One-off context packs copied into agent sessions.
- Local memory commands.
- Release, prompt, token, and evidence reports.

The CLI should not be required for product integrations. If users must run `opencontext` before
the integration works, prefer moving that setup into the host application through `setup_project()`.
