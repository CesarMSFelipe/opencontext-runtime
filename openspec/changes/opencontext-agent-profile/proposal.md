# Proposal: OpenContext Agent Profile

## Intent

Make OpenContext install/configure a first-class **OpenContext SDD/TDD profile** for supported coding agents. The profile should be direct, low-verbosity, TDD-ready, and governed by OpenContext rules. It must not inherit agentic workflow tool behavior, but it should cover the useful workflow controls users expect: auto/manual execution, artifact persistence mode (`engram`, `openspec`, `hybrid`, `none`), strict/ask/off TDD, compact context packs, traceable gates, and resumable artifacts.

## Scope

### In Scope
- Add an `opencontext` orchestration profile type.
- Make Codex and OpenCode-family setup use the OpenContext profile instead of raw `solo-compact`/hardcoded OpenCode assumptions.
- Persist SDD/TDD mode, model profile, artifact mode, and execution mode in generated project context.
- Keep generated agent instructions direct and low-verbosity.
- Add tests proving Codex/OpenCode receive the OpenContext profile and TDD rules.

### Out of Scope
- Reimplementing agentic workflow tool internals.
- Enabling external providers or network by default.
- Building UI flows beyond setup/config fields.
- Full graph-aware retrieval convergence; that remains the next feature track.

## Capabilities

### New Capabilities
- `agent-setup`: OpenContext installs agent SDD/TDD profiles with configurable execution and persistence modes.

### Modified Capabilities
- None.

## Approach

Introduce a reusable OpenContext-guided profile in `sdd_profiles.py`, expose it through existing setup/context artifacts, and update generated agent instructions/tests. Treat Codex/OpenCode as clients that consume OpenContext's own profile, not as owners of separate SDD semantics.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `opencontext_core/sdd_profiles.py` | Modified | Add `opencontext` profile type/instructions and map selected agents. |
| `opencontext_core/sdd_runtime.py` | Modified | Persist execution/artifact modes and direct profile instructions. |
| `opencontext_cli/commands/setup_cmd.py` | Modified | Configure selected agents with OpenContext profile defaults. |
| `tests/core/test_client_orchestrator_profiles.py` | Modified | Cover new profile behavior. |
| `.opencontext/sdd/*` | Modified | Project-local config should reflect OpenContext profile. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Breaking existing agent tests expecting `solo-compact` | Medium | Update tests to assert profile intent and keep per-client details in instructions. |
| Over-verbose generated instructions | Medium | Use direct rule lists and short phase guidance. |
| Ambiguous execution/persistence defaults | Medium | Defaults: `execution_mode=auto`, `artifact_mode=hybrid`, `tdd_mode=strict` when tests exist. |

## Rollback Plan

Revert the profile mapping and generated context fields to prior `solo-compact`/`multi-phase` values; regenerate `.opencontext/sdd/context.json` with existing setup command.

## Dependencies

- Existing SDD profile registry.
- Existing artifact store modes.
- Existing setup command.

## Success Criteria

- [ ] Codex setup produces `opencontext` profile, not raw `solo-compact`.
- [ ] OpenCode-family setup produces `opencontext` profile with multi-phase-compatible guidance.
- [ ] Generated context includes TDD, execution mode, and artifact mode.
- [ ] Tests pass for profile mapping and generated files.
