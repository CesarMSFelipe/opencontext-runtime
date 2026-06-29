# OpenContext Architecture Decision Records
## Version 1.0 (Draft)
### Document ID
OC-ADR-001

# Purpose

This document defines the Architecture Decision Record (ADR) process for OpenContext.

ADRs are used when a technical decision affects architecture, public contracts, workflow behaviour, runtime governance, safety, extensibility or long-term maintainability.

# Why ADRs Exist

OpenContext is designed as an Engineering Operating System.

A system of this size cannot rely on implicit decisions scattered across code, comments, issues or conversations.

Every significant architectural choice must be:

- explicit
- dated
- justified
- reversible when possible
- linked to evidence
- linked to affected contracts
- linked to benchmarks when applicable

# When an ADR Is Required

An ADR is required when a change:

- introduces a new public contract
- changes an existing public contract
- changes runtime execution semantics
- changes workflow behaviour
- changes policy enforcement
- changes memory persistence
- changes KG schema
- changes plugin APIs
- introduces a new harness category
- introduces a new workflow
- changes default configuration
- affects safety or security
- affects first-run UX
- affects benchmark methodology
- creates an exception to the Engineering Constitution

# When an ADR Is Not Required

An ADR is usually not required for:

- typo fixes
- internal refactors without behavioural change
- test-only changes
- documentation clarifications
- non-public implementation details
- small bug fixes that preserve contracts

# ADR Location

ADRs live in:

```text
docs/architecture/adrs/
```

Naming convention:

```text
ADR-0001-runtime-is-workflow-neutral.md
ADR-0002-sdd-and-oc-flow-coexist.md
ADR-0003-context-is-budgeted.md
```

# ADR Statuses

```text
proposed
accepted
superseded
rejected
deprecated
```

# ADR Template

```md
# ADR-0000: Title

## Status

Proposed | Accepted | Superseded | Rejected | Deprecated

## Date

YYYY-MM-DD

## Context

What problem are we solving?

## Decision

What decision are we making?

## Rationale

Why is this the right decision?

## Alternatives Considered

What else was considered?

## Consequences

What becomes easier?
What becomes harder?

## Affected Components

- Runtime
- Workflow
- Harness
- Skill
- Persona
- KG
- Memory
- Policy
- Plugin
- Studio

## Affected Public Contracts

List schemas or APIs affected.

## Benchmarks / Evidence

How will this be validated?

## Migration Plan

How do existing users/code migrate?

## Rollback Plan

How can this be undone?

## Links

Issues, PRs, docs, artifacts.
```

# Required Initial ADRs

## ADR-0001 — Runtime is workflow-neutral

Decision:

The Runtime executes workflow definitions and must not hardcode SDD or OC Flow semantics.

## ADR-0002 — SDD and OC Flow coexist

Decision:

SDD remains a first-class workflow. OC Flow is added as an independent operational workflow.

## ADR-0003 — Sessions are first-class

Decision:

Every run belongs to a session. Sessions are the top-level execution container.

## ADR-0004 — Context is budgeted

Decision:

Every context retrieval operation has a budget, omissions and evidence references.

## ADR-0005 — Mutations require receipts

Decision:

Every mutating operation must produce a receipt and checkpoint.

## ADR-0006 — Personas are responsibilities, not personalities

Decision:

Personas model engineering roles and must produce typed outputs.

## ADR-0007 — Skills are contracts, not prompt snippets

Decision:

Skills are reusable engineering procedures with inputs, outputs, gates and benchmarks.

## ADR-0008 — Harnesses are deterministic governance components

Decision:

Harnesses validate engineering behaviour and are not prompts.

## ADR-0009 — Memory is evidence-backed

Decision:

Durable memory requires evidence, classification, conflict detection and promotion policy.

## ADR-0010 — KG facts require provenance

Decision:

Non-structural or inferred KG facts must include evidence references.

## ADR-0011 — Runtime Intelligence proposes, Runtime governs

Decision:

Cost/confidence/evolution systems may recommend but may not silently override Runtime policy.

## ADR-0012 — Plugins integrate through public contracts

Decision:

Plugins may not depend on Runtime internals.

# ADR Review Rules

A PR requiring an ADR cannot be merged until:

- ADR exists;
- status is accepted or explicitly proposed for experimental work;
- affected contracts are listed;
- benchmarks/evidence are defined;
- migration impact is described.

# ADR Supersession

When an ADR is superseded:

- do not delete it;
- mark status as superseded;
- link to replacement ADR;
- describe migration impact.

# ADR Relationship with Roadmap

Roadmap phases may reference ADRs.

Any roadmap phase introducing new architecture should have at least one ADR.

# ADR Relationship with Benchmarks

If an ADR claims an improvement, it should define a benchmark.

Example:

```text
Claim: surgical context reduces token usage.
Benchmark: first-run bugfix context retrieval.
Metric: token usage reduced by 40% without lowering success rate.
```

# ADR Relationship with Constitution

Any ADR that violates or weakens the Engineering Constitution must explicitly state:

- which principle is affected;
- why the exception is necessary;
- how risk is mitigated;
- when the exception expires or will be revisited.

# Invariants

1. Significant architecture decisions are recorded.
2. ADRs are immutable after acceptance except for status updates.
3. Superseded ADRs remain visible.
4. Public contract changes require ADRs.
5. Safety-affecting changes require ADRs.
6. Benchmark claims require evidence.
7. Exceptions to the Constitution require explicit justification.

# Definition of Done

The ADR process is implemented when:

- ADR template exists.
- Initial ADRs exist.
- PR checklist references ADRs.
- Architecture docs link to ADRs.
- Public contract changes require ADR review.
- Supersession process is documented.

# Final Statement

ADRs are OpenContext's architectural memory.

They prevent the system from forgetting why it was designed the way it was.
