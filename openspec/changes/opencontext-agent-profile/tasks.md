# Tasks: OpenContext Agent Profile

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 120-220 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single work unit |
| Delivery strategy | auto-chain not needed |
| Chain strategy | single change |

Decision needed before apply: No
Chained PRs recommended: No
400-line budget risk: Low

## Phase 1: Profile Model

- [x] 1.1 Add `opencontext` to `ORCHESTRATOR_TYPES`.
- [x] 1.2 Add `_opencontext_instructions()` with direct SDD/TDD rules.
- [x] 1.3 Map Codex/OpenCode-family clients to `opencontext` profile where appropriate.

## Phase 2: SDD Context Controls

- [x] 2.1 Add `execution_mode` and `artifact_mode` to `SDDContext`.
- [x] 2.2 Pass defaults through `build_sdd_context()` / `write_sdd_context()`.
- [x] 2.3 Render these modes in `testing.md`.

## Phase 3: Setup Integration

- [x] 3.1 Ensure setup writes Codex/OpenCode clients with OpenContext profile.
- [x] 3.2 Keep TDD strict/ask/off configurable.
- [x] 3.3 Preserve existing setup command compatibility.

## Phase 4: Tests

- [x] 4.1 Update profile tests.
- [x] 4.2 Add context mode tests.
- [x] 4.3 Run focused test file.

## Phase 5: Project Config

- [x] 5.1 Regenerate/update `.opencontext/sdd/context.json` for this repo.
- [x] 5.2 Update `.opencontext/sdd/testing.md` and `.opencontext/agents/codex.md` if needed.

## Verification

- `python3 -m pytest tests/core/test_client_orchestrator_profiles.py -q` — passed.
- `python3 -m pytest tests/core/test_client_orchestrator_profiles.py tests/core/test_agent_integration_generator.py tests/core/test_sdd_runtime.py -q` — passed.
- `python3 -m ruff check packages/opencontext_core/opencontext_core/sdd_profiles.py packages/opencontext_core/opencontext_core/sdd_runtime.py packages/opencontext_core/opencontext_core/user_prefs.py packages/opencontext_cli/opencontext_cli/commands/setup_cmd.py packages/opencontext_cli/opencontext_cli/main.py tests/core/test_client_orchestrator_profiles.py` — passed.
