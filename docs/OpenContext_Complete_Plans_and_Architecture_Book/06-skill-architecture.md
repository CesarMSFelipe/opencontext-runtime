# OpenContext Skill Architecture
## Version 1.0 (Draft)
### Document ID
OC-SKILLS-001

## Purpose

This document defines the Skill Architecture used by the OpenContext Runtime.

Skills are reusable engineering capabilities. They are **not prompts** and they are **not workflows**.

A skill encapsulates a repeatable engineering procedure that can be invoked by multiple personas across multiple workflows.

---

# Core Principles

- Skills are composable.
- Skills are deterministic where possible.
- Skills never orchestrate workflows.
- Skills never bypass policies.
- Skills are independently benchmarked.
- Skills expose contracts.
- Skills are versioned.

---

# Runtime Position

```text
Workflow
  -> Persona
      -> Skill Bundle
          -> Skill
              -> Harness
                  -> Runtime
```

---

# Skill Definition

```yaml
schema_version: opencontext.skill.v1
id: oc-apply-surgical
name: Surgical Apply
version: 1.0
tier: core
category: mutation

trigger:
  workflow_nodes:
    - mutate

inputs:
  - task_contract
  - focused_context

outputs:
  - apply_edit
  - receipt

required_harnesses:
  - mutation
  - policy

required_capabilities:
  - apply_edit

token_budget: 1200

failure_modes:
  - policy_denied
  - invalid_contract
```

---

# Skill Lifecycle

```text
Resolve
↓
Validate Inputs
↓
Execute
↓
Validate Output Contract
↓
Emit Receipt
↓
Return
```

---

# Skill Categories

## Context

- oc-context-discovery
- oc-symbol-retrieval
- oc-owner-discovery
- oc-test-discovery
- oc-memory-grounding

## Planning

- oc-plan-lite
- oc-task-decomposition
- oc-acceptance-criteria
- oc-risk-evaluation

## Mutation

- oc-apply-surgical
- oc-refactor-safe
- oc-api-update
- oc-doc-update

## Inspection

- oc-local-first-validation
- oc-test-selection
- oc-lint-analysis
- oc-ast-review

## Diagnosis

- oc-three-hypotheses
- oc-root-cause-analysis
- oc-instrumentation
- oc-semantic-gc

## Review

- oc-review-changes
- oc-security-review
- oc-performance-review
- oc-maintainability-review

## Consolidation

- oc-memory-candidate
- oc-kg-update
- oc-summary
- oc-receipt-finalization

---

# Skill Bundles

Bundles are persona-specific.

Example:

```yaml
oc-builder:
  - oc-apply-surgical
  - oc-local-first-validation
  - oc-refactor-safe
```

```yaml
oc-diagnostician:
  - oc-three-hypotheses
  - oc-root-cause-analysis
  - oc-semantic-gc
```

---

# Skill Metadata

Every skill defines:

- id
- version
- owner
- maturity
- workflows
- personas
- required harnesses
- required capabilities
- token budget
- benchmark score
- confidence score

---

# Harness Integration

Every skill explicitly declares required harnesses.

Examples:

- Context Harness
- Mutation Harness
- Inspection Harness
- Security Harness
- Memory Harness
- KG Harness

The Runtime resolves them automatically.

---

# Output Contracts

Every skill returns a typed contract.

Examples:

- ApplyEdit
- TaskContract
- ReviewReport
- DiagnosisAttempt
- ContextEnvelope
- MemoryCandidate

Free-form text is never consumed by the Runtime.

---

# Benchmarking

Every skill must be benchmarked independently.

Metrics:

- success rate
- token cost
- latency
- retry rate
- correctness
- confidence

Poorly performing skills may be disabled automatically by policy.

---

# Plugin Skills

Plugins may contribute new skills.

Requirements:

- unique id
- version
- contract
- benchmarks
- compatibility declaration

Plugins cannot override core skills unless explicitly enabled.

---

# Migration

The existing skills in the current branch should migrate into SkillDefinition objects without changing behaviour.

New skills proposed in previous architecture plans (Agency Agents, VibeCode Pro Max Kit, Matt Pocock Skills, AIDD, Claude Protocol) should become first-class built-in skills grouped by category instead of prompt collections.

---

# Invariants

1. Skills are reusable.
2. Skills are workflow-neutral.
3. Skills never orchestrate execution.
4. Skills always emit receipts for meaningful actions.
5. Skills always return typed outputs.
6. Skills are benchmarked.
7. Skills are independently versioned.

---

# Definition of Done

Implemented when:

- SkillRegistry exists.
- SkillDefinition schema exists.
- Personas resolve bundles dynamically.
- Skills are benchmarked.
- Skills expose contracts.
- Plugin skills load safely.
- Runtime validates outputs.

---

# Final Statement

Skills are the reusable engineering vocabulary of OpenContext.

Workflows define **when** something happens.

Personas define **who** is responsible.

Skills define **how** reusable engineering work is performed.
