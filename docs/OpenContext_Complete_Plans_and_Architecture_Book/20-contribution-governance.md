# OpenContext Contribution & Governance Architecture
## Version 1.0 (Draft)
### Document ID
OC-GOVERNANCE-001

# Purpose

This document defines how OpenContext contributions are proposed, reviewed, validated, benchmarked and merged.

Governance exists to keep the project coherent as Runtime, SDD, OC Flow, Skills, Personas, Harnesses, KG, Memory, Plugins and Studio evolve.

# Core Principles

1. Every significant change must map to an architecture document.
2. Every public contract change requires an ADR.
3. Every behavioural change requires tests or benchmarks.
4. Every new workflow, skill, persona, harness or plugin must declare ownership and contracts.
5. Compatibility is preserved unless an ADR approves breaking change.
6. First-run quality must not regress.
7. Security gates must not weaken silently.
8. Runtime internals remain replaceable.
9. Evidence beats opinion.
10. Documentation is part of implementation.

# Contribution Types

## Runtime Change

Changes execution, sessions, events, artifacts, receipts, workflow execution or state transitions.

Requires:

- tests
- ADR if public behaviour changes
- migration notes
- benchmark when performance or success rate is affected

## Workflow Change

Changes SDD, OC Flow or adds a workflow.

Requires:

- WorkflowDefinition update
- affected harnesses
- affected personas
- affected skills
- benchmark
- documentation

## Skill Change

Adds or changes a skill.

Requires:

- SkillDefinition
- output contract
- gates
- examples
- benchmark or test
- routing validation

## Persona Change

Adds or changes a persona.

Requires:

- PersonaDefinition
- responsibilities
- tool permissions
- compatible workflows/nodes
- output contracts

## Harness Change

Adds or changes a harness.

Requires:

- HarnessDefinition
- gates
- HarnessResult
- receipts
- benchmark
- failure modes

## KG / Memory Change

Requires:

- schema update if needed
- provenance handling
- migration
- retrieval benchmark
- conflict/staleness behaviour

## Plugin Change

Requires:

- PluginManifest
- permissions
- compatibility check
- isolation
- benchmark if executable

# Pull Request Checklist

Every PR must answer:

1. Which architecture document does this implement?
2. Which contract does this introduce or modify?
3. Does this affect SDD?
4. Does this affect OC Flow?
5. Does this affect first-run UX?
6. Does this affect token usage?
7. Does this affect policies or security?
8. Does this require an ADR?
9. Which tests or benchmarks prove it works?
10. What is the rollback path?

# Review Levels

## Level 1 — Internal Refactor

- no public contract change
- no runtime behaviour change
- normal tests required

## Level 2 — Behaviour Change

- runtime/workflow behaviour changes
- tests and docs required
- ADR may be required

## Level 3 — Public Contract Change

- schema/API/plugin-facing change
- ADR required
- migration required
- compatibility review required

## Level 4 — Safety-Critical Change

- policy/security/provider/mutation behaviour changes
- ADR required
- security benchmark required
- maintainer approval required

# Required Checks

Minimum CI checks:

- unit tests
- type/static checks
- formatting
- first-run smoke benchmark
- SDD smoke benchmark
- OC Flow smoke benchmark
- policy/security tests
- schema validation
- docs link validation

# Architecture Review

Architecture review is required for:

- new public contracts
- workflow changes
- runtime state changes
- policy changes
- plugin API changes
- KG/memory schema changes
- benchmark methodology changes

# Documentation Rules

A change is incomplete if documentation is missing for:

- new config keys
- new public contracts
- new workflow nodes
- new skill/persona/harness definitions
- new policy behaviour
- new plugin capability
- migration steps

# Versioning

OpenContext uses semantic versioning for public contracts.

Internal implementation may change freely.

Public contracts follow:

- experimental
- beta
- stable
- deprecated
- removed

Breaking stable contracts requires major version or approved migration path.

# Release Governance

A release requires:

- passing full benchmark suite
- updated architecture docs
- updated changelog
- migration notes
- contract compatibility report
- security review
- first-run validation

# Maintainer Responsibilities

Maintainers ensure:

- architecture consistency
- compatibility
- safety
- benchmark quality
- documentation quality
- plugin ecosystem health
- first-run experience

# Contributor Responsibilities

Contributors ensure:

- minimal scope
- tests
- documentation
- contract compliance
- policy compliance
- migration notes when needed

# Decision Records

Any architectural disagreement should be resolved through ADRs, not hidden implementation choices.

# Invariants

1. No hidden architecture decisions.
2. No public contract changes without review.
3. No safety regression without explicit approval.
4. No first-run regression.
5. No undocumented config.
6. No plugin bypass of Runtime.
7. No workflow-specific infrastructure duplication.
8. No benchmark claims without benchmark evidence.

# Definition of Done

Governance is implemented when:

- PR template exists.
- ADR process exists.
- CI validates schemas.
- benchmarks run.
- architecture docs are referenced by PRs.
- contract compatibility is checked.
- release process is documented.
- contributors can safely extend the system.

# Final Statement

Governance is how OpenContext scales without losing coherence.

A powerful runtime needs strong engineering discipline around it.
