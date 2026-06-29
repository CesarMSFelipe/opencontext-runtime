# OpenContext Architecture Documentation Index
## Version 1.0 (Draft)
### Document ID
OC-DOCS-INDEX-001

### Status
Draft

---

# 1. Purpose

This document is the master index for the OpenContext architecture specification.

It explains the purpose of each architecture document, recommended reading order and how contributors should use the documentation when designing, reviewing or implementing OpenContext features.

---

# 2. Documentation Goals

The architecture documentation exists to make OpenContext:

- understandable;
- implementable;
- reviewable;
- extensible;
- governable;
- benchmarkable;
- stable over time.

These documents are not passive reference material.

They are the technical constitution of the project.

---

# 3. Recommended Reading Order

## Foundation

1. `00-engineering-principles.md`
2. `01-system-architecture.md`
3. `02-runtime-architecture.md`

These define why OpenContext exists, how the system is structured and how execution works.

## Workflows

4. `03-sdd-workflow-architecture.md`
5. `04-oc-flow-architecture.md`

These define the two first-class workflows.

## Execution Roles

6. `05-persona-architecture.md`
7. `06-skill-architecture.md`
8. `07-harness-architecture.md`

These define who performs work, how reusable work is represented and how quality is enforced.

## Cognitive Runtime

9. `08-knowledge-graph-architecture.md`
10. `09-memory-architecture.md`
11. `10-context-engineering-architecture.md`

These define how OpenContext knows the codebase, remembers durable knowledge and minimizes token usage.

## Intelligence and Governance

12. `11-runtime-intelligence-architecture.md`
13. `15-policy-security-architecture.md`
14. `14-observability-benchmark-architecture.md`

These define cost/confidence, runtime measurement, security and evaluation.

## Platform

15. `12-plugin-extension-architecture.md`
16. `13-configuration-ux-architecture.md`
17. `22-studio-architecture.md`
18. `23-mcp-cli-adapter-architecture.md`

These define extensibility and user-facing surfaces.

## Lifecycle

19. `16-roadmap-implementation.md`
20. `17-public-contracts-api-specification.md`
21. `18-architecture-decision-records.md`
22. `20-contribution-governance.md`
23. `21-testing-benchmark-strategy.md`
24. `24-artifact-receipt-lifecycle.md`
25. `25-provider-model-gateway.md`
26. `26-organization-graph-team-topology.md`
27. `27-release-versioning-migration.md`

These define implementation, contracts, releases, governance and migration.

---

# 4. Document Catalogue

## 00 — Engineering Principles

Defines the engineering philosophy of OpenContext.

Use this document when deciding whether a feature belongs in the project.

## 01 — System Architecture

Defines the top-level architecture and subsystem boundaries.

Use this document when deciding where a feature should live.

## 02 — Runtime Architecture

Defines sessions, runs, workflow execution, events, artifacts and runtime responsibilities.

Use this document when modifying execution behaviour.

## 03 — SDD Workflow Architecture

Defines the formal spec-driven workflow.

Use this document when changing SDD phases or SDD semantics.

## 04 — OC Flow Architecture

Defines the operational local-first agentic workflow.

Use this document when implementing bugfix/refactor/maintenance execution.

## 05 — Persona Architecture

Defines personas as engineering responsibilities.

Use this document when adding or changing personas.

## 06 — Skill Architecture

Defines skills as reusable engineering capabilities.

Use this document when adding or changing skills.

## 07 — Harness Architecture

Defines harnesses as deterministic governance components.

Use this document when adding validation, inspection, diagnosis, security or consolidation behaviour.

## 08 — Knowledge Graph Architecture

Defines the code and organization knowledge graph.

Use this document when changing indexing, retrieval, graph schema or impact analysis.

## 09 — Memory Architecture

Defines durable project memory.

Use this document when changing memory persistence, retrieval or promotion.

## 10 — Context Engineering & Compression Architecture

Defines context envelopes, context layers and semantic compression.

Use this document when changing retrieval or prompt construction.

## 11 — Runtime Intelligence Architecture

Defines cost engine, confidence engine, simulator, profiler, health and evolution.

Use this document when adding measurement, optimization or self-improvement features.

## 12 — Plugin & Extension Architecture

Defines extension points and plugin contracts.

Use this document when exposing new plugin APIs.

## 13 — Configuration & UX Architecture

Defines configuration profiles, CLI UX and first-run behaviour.

Use this document when adding config keys or changing user experience.

## 14 — Observability & Benchmark Architecture

Defines telemetry, traces, metrics and benchmark strategy.

Use this document when adding instrumentation or evaluation.

## 15 — Policy & Security Architecture

Defines runtime-enforced policy and security rules.

Use this document when changing permissions, file access, commands, secrets, network or provider behaviour.

## 16 — Roadmap & Implementation Plan

Defines the migration path from the current branch to the target architecture.

Use this document when planning PRs.

## 17 — Public Contracts & API Specification

Defines stable contracts for runtime, workflows, plugins and external interfaces.

Use this document when adding or changing schemas.

## 18 — Architecture Decision Records

Defines the ADR process.

Use this document when making significant architectural decisions.

## 19 — Engineering Constitution

A condensed rulebook version of the engineering principles.

Use this as the quick governance checklist.

## 20 — Contribution & Governance

Defines PR expectations, review levels and release discipline.

Use this document when contributing.

## 21 — Testing & Benchmark Strategy

Defines required tests and benchmarks.

Use this document when validating implementation quality.

## 22 — Studio Architecture

Defines the visual control plane.

Use this document when adding Studio views or UI integrations.

## 23 — MCP, CLI & Adapter Architecture

Defines external interfaces.

Use this document when changing MCP tools, CLI commands or IDE adapters.

## 24 — Artifact, Receipt & Lifecycle Architecture

Defines durable outputs, receipts, checkpoints and rollback.

Use this document when changing persistence of execution evidence.

## 25 — Provider Gateway & Model Routing Architecture

Defines provider abstraction, routing, fallback and cost tracking.

Use this document when adding model providers.

## 26 — Organization Graph & Team Topology Architecture

Defines owners, teams, services, escalation and org-aware runtime behaviour.

Use this document when adding team or service awareness.

## 27 — Release, Versioning & Migration Architecture

Defines versioning, migration, deprecation and release strategy.

Use this document when preparing releases or changing stable contracts.

---

# 5. Contributor Usage

Before implementing a feature, contributors should identify:

1. Which architecture document applies?
2. Which public contract is affected?
3. Which workflow is affected?
4. Which harness validates it?
5. Which benchmark proves it?
6. Which ADR is required, if any?

If no architecture document applies, the feature may require a new architecture document or an ADR.

---

# 6. PR Reference Format

Every major PR should include:

```md
Architecture:
- OC-RUNTIME-001
- OC-HARNESSES-001

Contracts:
- RuntimeEvent
- HarnessResult

Benchmarks:
- first-run
- oc-flow-bugfix

ADR:
- ADR-0008
```

---

# 7. Documentation Maintenance

Architecture documentation must be updated when:

- public contracts change;
- workflow semantics change;
- runtime behaviour changes;
- policy rules change;
- plugin APIs change;
- KG or memory schemas change;
- first-run UX changes;
- benchmark methodology changes.

---

# 8. Document Statuses

Documents may have statuses:

```text
draft
accepted
deprecated
superseded
```

Draft documents guide implementation but may evolve.

Accepted documents require ADR for major changes.

---

# 9. Architecture Book Layout

Recommended repository layout:

```text
docs/
  architecture/
    00-engineering-principles.md
    01-system-architecture.md
    02-runtime-architecture.md
    03-sdd-workflow-architecture.md
    04-oc-flow-architecture.md
    05-persona-architecture.md
    06-skill-architecture.md
    07-harness-architecture.md
    08-knowledge-graph-architecture.md
    09-memory-architecture.md
    10-context-engineering-architecture.md
    11-runtime-intelligence-architecture.md
    12-plugin-extension-architecture.md
    13-configuration-ux-architecture.md
    14-observability-benchmark-architecture.md
    15-policy-security-architecture.md
    16-roadmap-implementation.md
    17-public-contracts-api-specification.md
    18-architecture-decision-records.md
    19-engineering-constitution.md
    20-contribution-governance.md
    21-testing-benchmark-strategy.md
    22-studio-architecture.md
    23-mcp-cli-adapter-architecture.md
    24-artifact-receipt-lifecycle.md
    25-provider-model-gateway.md
    26-organization-graph-team-topology.md
    27-release-versioning-migration.md
    28-docs-index.md
```

---

# 10. Final Statement

The architecture documents are not optional.

They are how OpenContext remains coherent as it grows.

A contribution that improves code while weakening the architecture is not an improvement.
