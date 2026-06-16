# Design: OpenContext Agent Profile

## Technical Approach

Add a profile type named `opencontext` to the SDD profile registry. Keep client identity (`codex`, `opencode`) separate from profile semantics (`opencontext`). Generated context will expose client → profile mapping plus SDD controls: `execution_mode`, `artifact_mode`, `tdd_mode`, `sdd_model_profile`.

## Architecture Decisions

### Decision: Add `opencontext` as orchestration profile type

**Choice**: Extend `ORCHESTRATOR_TYPES` with `opencontext` and provide `_opencontext_instructions()`.
**Alternatives considered**: Reuse `solo-compact`; reuse `multi-phase`; clone agentic workflow tool behavior.
**Rationale**: The product needs OpenContext-owned semantics across clients, not client-owned SDD semantics.

### Decision: Keep generated instructions short

**Choice**: Short phase rules with context-pack-first, TDD-first, trace-first language.
**Alternatives considered**: Long workflow manuals in every generated file.
**Rationale**: User wants direct, low-verbosity setup.

### Decision: Add SDD control fields to context

**Choice**: Add `execution_mode` and `artifact_mode` to `SDDContext`.
**Alternatives considered**: Store only in global user prefs or harness yaml.
**Rationale**: Agents read `.opencontext/sdd/context.json`; controls must be project-local and visible.

## Data Flow

    setup command
      └─ selected agents + tdd/profile/modes
          └─ write_sdd_context()
              ├─ SDDContext JSON
              ├─ testing.md
              └─ generated agent files

## File Changes

| File | Action | Description |
|---|---|---|
| `packages/opencontext_core/opencontext_core/sdd_profiles.py` | Modify | Add OpenContext profile and map agent profiles. |
| `packages/opencontext_core/opencontext_core/sdd_runtime.py` | Modify | Add execution/artifact fields and render docs. |
| `packages/opencontext_cli/opencontext_cli/commands/setup_cmd.py` | Modify | Pass/default SDD controls into context. |
| `tests/core/test_client_orchestrator_profiles.py` | Modify | Update/add assertions. |
| `.opencontext/sdd/context.json` | Regenerate | Reflect local project profile. |
