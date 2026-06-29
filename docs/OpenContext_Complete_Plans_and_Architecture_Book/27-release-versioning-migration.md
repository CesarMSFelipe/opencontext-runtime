# OpenContext Release, Versioning & Migration Architecture
## Version 1.0 (Draft)
### Document ID
OC-RELEASE-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `16-roadmap-implementation.md`
- `17-public-contracts-api-specification.md`
- `18-architecture-decision-records.md`
- `20-contribution-governance.md`

---

# 1. Purpose

This document defines how OpenContext versions, releases, deprecates and migrates its runtime, workflows, public contracts, plugins, configuration, Knowledge Graph, memory and user-facing interfaces.

OpenContext must evolve quickly without breaking trust.

Versioning is how the project protects users, plugin authors and contributors while allowing the architecture to improve.

---

# 2. Mission

The release and migration system must ensure that:

- existing users can upgrade safely;
- public contracts remain stable;
- breaking changes are explicit;
- deprecations are gradual;
- migrations are automated where possible;
- old runs remain readable;
- plugins can declare compatibility;
- benchmarks validate releases;
- rollback is possible.

---

# 3. Core Principles

1. Public contracts are versioned.
2. Runtime internals may evolve behind stable contracts.
3. Breaking changes require ADRs.
4. Migrations must be explicit.
5. Releases require benchmarks.
6. Existing session artifacts must remain readable.
7. Configuration upgrades should be automated when safe.
8. Plugin compatibility must be machine-checkable.
9. Deprecations must be announced before removal.
10. Rollback must be considered before release.

---

# 4. Versioned Components

The following components have independent versioning concerns:

- OpenContext Runtime
- Workflow definitions
- Public contracts
- Configuration schema
- Persona definitions
- Skill definitions
- Harness definitions
- Plugin manifests
- Knowledge Graph schema
- Memory schema
- Artifact schema
- Receipt schema
- Event schema
- MCP tool schemas
- Studio data contracts
- Provider adapters
- Benchmark suites

---

# 5. Semantic Versioning

OpenContext follows semantic versioning for stable public releases:

```text
MAJOR.MINOR.PATCH
```

## MAJOR

Breaking changes to stable public contracts.

## MINOR

Backward-compatible new functionality.

## PATCH

Bug fixes and non-breaking improvements.

---

# 6. Stability Levels

Every public contract and extension point has a stability level.

```text
experimental
beta
stable
deprecated
removed
```

## experimental

May change at any time.

## beta

Expected to stabilize, but breaking changes are possible with migration notes.

## stable

Breaking changes require major version or explicit compatibility layer.

## deprecated

Still supported but scheduled for removal.

## removed

No longer available.

---

# 7. Contract Versioning

Every public schema must include:

```yaml
schema_version: opencontext.<contract>.v1
```

Example:

```yaml
schema_version: opencontext.workflow.v1
```

Breaking schema changes require:

```yaml
schema_version: opencontext.workflow.v2
```

---

# 8. Runtime Version

The runtime exposes:

```bash
opencontext version
```

Output:

```json
{
  "opencontext": "1.0.0",
  "runtime_api": "v1",
  "workflow_schema": "v1",
  "plugin_api": "v1",
  "config_schema": "v2",
  "kg_schema": "v2",
  "memory_schema": "v1"
}
```

---

# 9. Configuration Migration

Configuration schema is versioned.

Primary file:

```text
opencontext.yaml
```

Example:

```yaml
version: 2
profile: balanced
```

When config version changes, OpenContext must provide:

```bash
opencontext config migrate
opencontext config migrate --dry-run
```

Dry-run output:

```text
Config migration v1 -> v2

Added:
  runtime.resume: true
  context.strategy: surgical_first

Renamed:
  harness.approval_required_for_writes -> policies.auto_apply

Removed:
  none
```

---

# 10. Workflow Migration

Workflow definitions are versioned.

Example:

```yaml
schema_version: opencontext.workflow.v1
id: oc-flow
version: 1.0.0
```

Workflow migration must preserve:

- active sessions;
- archived runs;
- artifacts;
- receipts;
- event readability.

If a workflow node changes name, a migration map is required.

---

# 11. Session Migration

Old sessions must remain readable.

Session migration should support:

```bash
opencontext session migrate <session_id>
opencontext session migrate --all
```

Migration should never mutate original data without backup.

---

# 12. Artifact and Receipt Compatibility

Artifacts and receipts are audit records.

They must remain readable indefinitely when possible.

If schemas evolve:

- old schemas remain supported for reading;
- new writes use current schema;
- migration is optional unless required for resume.

---

# 13. Knowledge Graph Migration

KG schema migrations must be explicit.

Examples:

- node type added;
- edge type renamed;
- temporal metadata added;
- evidence format changed.

Commands:

```bash
opencontext kg migrate
opencontext kg migrate --dry-run
opencontext kg rebuild
```

If migration is unsafe, rebuild from source is allowed.

---

# 14. Memory Migration

Memory migrations must preserve provenance.

Commands:

```bash
opencontext memory migrate
opencontext memory audit
```

Migration must not silently promote or delete memories.

Deprecated memories should be marked stale/superseded, not erased.

---

# 15. Plugin Compatibility

Plugin manifests declare supported versions.

```yaml
requires:
  opencontext: ">=1.0,<2.0"
  plugin_api: "v1"
  workflow_schema: "v1"
```

If incompatible:

- plugin is disabled;
- user receives actionable explanation;
- runtime continues without plugin if possible.

---

# 16. MCP Compatibility

MCP tool schemas are public contracts.

Changes require:

- schema version update;
- backward-compatible aliases when possible;
- migration notes;
- client compatibility tests.

Existing tools should not be removed without deprecation period.

---

# 17. Studio Compatibility

Studio reads public contracts only.

Studio must support viewing older sessions where possible.

When Studio cannot render an old artifact, it should show raw artifact and schema version.

---

# 18. Provider Adapter Versioning

Provider adapters declare:

- supported runtime version;
- supported provider API versions;
- capabilities;
- structured output support;
- cost model version.

Provider failures due to version mismatch must be actionable.

---

# 19. Benchmark Versioning

Benchmarks are versioned because benchmark methodology changes can invalidate comparisons.

```yaml
benchmark_suite: first-run
version: 1.0.0
```

Benchmark reports must include suite version.

---

# 20. Release Channels

Supported channels:

```text
nightly
alpha
beta
rc
stable
lts
```

## nightly

Unstable development snapshots.

## alpha

Feature-complete enough for testing.

## beta

API mostly stable.

## rc

Release candidate; only critical fixes.

## stable

Recommended default.

## lts

Long-term support for enterprise users.

---

# 21. Feature Flags

Major new subsystems should ship behind feature flags before becoming default.

Examples:

```yaml
features:
  oc_flow: true
  runtime_intelligence: true
  plugin_sdk: false
  studio: false
```

Feature flags must be documented.

Experimental flags may change without full semver guarantee.

---

# 22. Deprecation Policy

Deprecation requires:

1. announcement;
2. warning in CLI/MCP output where relevant;
3. migration path;
4. replacement documented;
5. minimum support period.

Example:

```text
Deprecated in 1.2
Warned through 1.x
Removed in 2.0
```

---

# 23. Breaking Change Policy

Breaking changes require:

- ADR;
- migration guide;
- compatibility analysis;
- benchmark run;
- release note;
- major version unless experimental.

---

# 24. Rollback Strategy

Releases should support rollback when possible.

Rollback requires:

- previous config backup;
- session data preserved;
- old artifacts readable;
- migration backups;
- plugin disable path.

Commands:

```bash
opencontext migrate --backup
opencontext rollback <migration_id>
```

---

# 25. Release Checklist

Before release:

- unit tests pass;
- contract tests pass;
- SDD benchmark passes;
- OC Flow benchmark passes;
- first-run benchmark passes;
- security benchmark passes;
- plugin compatibility suite passes;
- docs updated;
- migration guide updated;
- changelog updated;
- public contracts frozen;
- release notes generated.

---

# 26. Changelog Format

Every release notes section should include:

- Added
- Changed
- Deprecated
- Removed
- Fixed
- Security
- Migration Notes
- Contract Changes
- Benchmark Results

---

# 27. Migration from `feat/agentic-engineering-runtime`

The migration from the current branch to OpenContext 1.0 should be staged:

## Stage 1

Wrap current runtime with sessions/events/artifacts.

## Stage 2

Introduce workflow registry and register SDD.

## Stage 3

Harden current SDD without changing user behaviour.

## Stage 4

Introduce OC Flow behind feature flag.

## Stage 5

Move personas/skills/harnesses to registries.

## Stage 6

Introduce KG/memory/context v2.

## Stage 7

Introduce Runtime Intelligence.

## Stage 8

Stabilize public contracts.

## Stage 9

Add plugin SDK.

## Stage 10

Release 1.0.

---

# 28. Compatibility Guarantees for 1.0

OpenContext 1.0 should guarantee stability for:

- Runtime API v1;
- Workflow schema v1;
- Persona schema v1;
- Skill schema v1;
- Harness schema v1;
- Plugin manifest v1;
- Event schema v1;
- Artifact schema v1;
- Receipt schema v1;
- Config schema v2.

---

# 29. Migration UX

Migration errors must be actionable.

Bad:

```text
Migration failed.
```

Good:

```text
Config migration failed because `workflow.default` references unknown workflow `full`.
Suggested fix: use `sdd` or keep compatibility alias enabled.
```

---

# 30. Invariants

1. Public contracts are versioned.
2. Breaking changes require ADR.
3. Stable APIs are not removed without deprecation.
4. Config migrations have dry-run.
5. Sessions remain readable.
6. Artifacts and receipts remain auditable.
7. Plugins declare compatibility.
8. Release candidates pass benchmarks.
9. Migration errors are actionable.
10. Rollback is considered for every migration.

---

# 31. Definition of Done

This architecture is implemented when:

- version command exists;
- config migration exists;
- session migration exists;
- KG/memory migration exists;
- plugin compatibility checks exist;
- release checklist exists;
- changelog format is adopted;
- deprecation warnings work;
- benchmark gates run before release;
- migration from current branch is documented.

---

# 32. Final Statement

OpenContext must evolve quickly without making users pay the cost of instability.

Versioning and migration are how the project earns long-term trust.
