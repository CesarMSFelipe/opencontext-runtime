# OpenContext Architecture Validation Matrix
## Version 1.0 (Draft)
### Document ID
OC-VALIDATION-001

# Purpose

This document defines how every OpenContext architecture principle, subsystem and roadmap epic is validated.

The Architecture Validation Matrix connects architecture documents to implementation artifacts, tests, benchmarks, runtime events and release gates.

---

# Mission

OpenContext must not rely on architecture documents as passive intent.

Every important architectural claim should be verifiable.

This document answers:

- How do we know the Runtime is workflow-neutral?
- How do we know SDD and OC Flow share infrastructure?
- How do we know context is budgeted?
- How do we know policies are enforced?
- How do we know plugins cannot bypass Runtime?
- How do we know first-run UX is good?

---

# Validation Dimensions

Each subsystem is validated across:

1. Contract
2. Runtime Behaviour
3. Tests
4. Benchmarks
5. Events
6. Receipts
7. Documentation
8. Studio Visibility
9. Release Gate

---

# Validation Matrix

| Area | Contract | Behaviour | Benchmark | Release Gate |
|---|---|---|---|---|
| Runtime | RuntimeApi | sessions/runs execute | first-run | required |
| SDD | WorkflowDefinition | all phases execute | sdd-suite | required |
| OC Flow | WorkflowDefinition | bugfix flow executes | oc-flow-suite | required |
| Personas | PersonaDefinition | registry resolution | persona-suite | required |
| Skills | SkillDefinition | bundle execution | skill-suite | required |
| Harnesses | HarnessDefinition | gates enforced | harness-suite | required |
| KG | KgNode/KgEdge | retrieval works | kg-suite | required |
| Memory | MemoryRecord | promotion works | memory-suite | required |
| Context | ContextEnvelope | budget enforced | context-suite | required |
| Policy | PolicyDecision | unsafe ops blocked | security-suite | required |
| Plugins | PluginManifest | permissions enforced | plugin-suite | required |
| Studio | Public contracts | views render | studio-smoke | recommended |

---

# Architectural Claims and Validation

## Claim: Runtime is workflow-neutral

Validated by:

- SDD runs through WorkflowRunner.
- OC Flow runs through WorkflowRunner.
- Adding a workflow does not modify Runtime Core.

Required tests:

- `test_workflow_registry_loads_sdd`
- `test_workflow_registry_loads_oc_flow`
- `test_runtime_executes_generic_workflow`

## Claim: Context is budgeted

Validated by:

- ContextEnvelope includes token estimate.
- Retrieval refuses unbounded context.
- Full-file retrieval creates receipt.

Required tests:

- `test_context_budget_enforced`
- `test_context_omissions_recorded`
- `test_full_file_requires_reason`

## Claim: Mutations require receipts

Validated by:

- ApplyEdit creates ApplyReceipt.
- Patch is persisted.
- Checkpoint exists before write.

Required tests:

- `test_apply_edit_creates_receipt`
- `test_apply_edit_creates_checkpoint`
- `test_patch_artifact_created`

## Claim: Policies are runtime-enforced

Validated by:

- forbidden path writes blocked;
- command policy enforced;
- provider calls redacted.

Required tests:

- `test_forbidden_path_blocked`
- `test_command_policy_denies_unsafe_command`
- `test_provider_redaction_runs`

## Claim: Memory is evidence-backed

Validated by:

- MemoryRecord requires evidence_refs.
- Memory Harness rejects speculative records.
- Supersession works.

Required tests:

- `test_memory_requires_evidence`
- `test_memory_rejects_cot`
- `test_memory_supersession`

## Claim: Plugins cannot bypass Runtime

Validated by:

- Plugin permissions enforced.
- Plugin components use public contracts.
- Direct unsafe access is blocked.

Required tests:

- `test_plugin_permission_denied`
- `test_plugin_contract_validation`
- `test_plugin_cannot_register_private_runtime_hook`

---

# Required Validation Artifacts

Each major PR should produce or update:

- unit tests;
- contract tests;
- benchmark results;
- architecture doc references;
- ADR when required;
- migration notes if applicable.

---

# Contract Validation

All public contracts must be validated with schema tests.

Required command:

```bash
opencontext dev validate-contracts
```

Checks:

- schema version exists;
- required fields exist;
- deprecated fields are marked;
- examples validate;
- plugin-facing contracts are stable.

---

# Workflow Validation

Required command:

```bash
opencontext dev validate-workflows
```

Checks:

- workflow graph is valid;
- start node exists;
- terminal nodes exist;
- no dead nodes;
- required personas exist;
- required skills exist;
- required harnesses exist;
- transitions are valid.

---

# Skill/Persona/Harness Validation

Required command:

```bash
opencontext dev validate-registries
```

Checks:

- duplicate IDs;
- invalid references;
- missing output contracts;
- missing token budgets;
- missing gates;
- invalid workflow/node compatibility.

---

# Benchmark Validation

Required command:

```bash
opencontext benchmark run smoke
```

Minimum smoke suite:

- first-run
- sdd-basic
- oc-flow-bugfix
- policy-deny
- plugin-load

---

# Release Validation

Before release:

```bash
opencontext release validate
```

Runs:

- contract validation;
- workflow validation;
- registry validation;
- benchmark suite;
- migration checks;
- docs index check;
- ADR status check.

---

# Studio Validation

Studio should validate that it can render:

- current session;
- historical session;
- failed run;
- escalated run;
- benchmark report;
- policy denial.

---

# Invariants

1. Architecture claims must be testable.
2. Every public contract has schema validation.
3. Every workflow has graph validation.
4. Every registry has reference validation.
5. Every release runs validation.
6. Benchmarks validate user-visible outcomes.
7. Documentation references are checked.
8. ADR requirements are enforced.

---

# Definition of Done

Architecture validation is complete when:

- validation commands exist;
- CI runs validation;
- release validation blocks bad releases;
- validation matrix is maintained;
- architecture documents map to tests/benchmarks;
- Studio can show validation status.

---

# Final Statement

Architecture is only real when the system enforces it.

The validation matrix turns architectural intent into executable quality gates.
