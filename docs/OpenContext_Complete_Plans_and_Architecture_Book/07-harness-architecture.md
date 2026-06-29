# OpenContext Harness Architecture
## Version 1.0 (Draft)
### Document ID
OC-HARNESSES-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `02-runtime-architecture.md`
- `03-sdd-workflow-architecture.md`
- `04-oc-flow-architecture.md`
- `05-persona-architecture.md`
- `06-skill-architecture.md`

---

# 1. Purpose

This document defines the Harness Architecture for OpenContext.

Harnesses are deterministic governance components used by workflows, personas and skills to ensure correctness, safety, observability, verification and repeatability.

A harness is not a prompt.

A harness is not a persona.

A harness is not a workflow.

A harness is an executable contract around engineering behaviour.

---

# 2. Core Principle

Harnesses exist to make agentic engineering reliable.

The language model may propose.

The harness validates.

The runtime enforces.

No workflow should depend on model goodwill for quality, safety or correctness.

---

# 3. Position in the Architecture

```text
Runtime
  -> Workflow Node
    -> Persona
      -> Skill
        -> Harness Registry
          -> Harness
            -> Gates
            -> Receipts
            -> Events
```

Harnesses are invoked by the Runtime.

Skills and workflow nodes declare required harnesses.

The Runtime resolves and executes them.

---

# 4. Harness Definition

```python
class HarnessDefinition(BaseModel):
    schema_version: str = "opencontext.harness.v1"
    id: str
    version: str
    type: str
    description: str
    default_mode: Literal["off", "warn", "strict"]
    required_capabilities: list[str]
    inputs: list[str]
    outputs: list[str]
    gates: list[str]
    metrics: list[str]
    receipts: list[str]
    failure_modes: list[str]
```

---

# 5. Harness Modes

Harnesses support three modes:

```text
off
warn
strict
```

## off

The harness is disabled.

## warn

The harness records findings but does not block execution.

## strict

The harness blocks execution when gates fail.

Profiles decide defaults.

---

# 6. Harness Registry

Suggested structure:

```text
opencontext_core/harnesses/
  registry.py
  definition.py
  runner.py
  gates.py
  results.py

  builtins/
    context.yaml
    planning.yaml
    protocol.yaml
    mutation.yaml
    inspection.yaml
    diagnosis.yaml
    review.yaml
    security.yaml
    escalation.yaml
    memory.yaml
    kg.yaml
    consolidation.yaml
    evaluation.yaml
```

---

# 7. Harness Execution Lifecycle

```text
Resolve Harness
↓
Load Inputs
↓
Check Capabilities
↓
Evaluate Policies
↓
Execute Checks
↓
Produce Gate Results
↓
Emit Events
↓
Create Receipts
↓
Return HarnessResult
```

---

# 8. HarnessResult

```python
class HarnessResult(BaseModel):
    schema_version: str = "opencontext.harness_result.v1"
    harness_id: str
    mode: str
    status: Literal["passed", "warning", "failed", "skipped"]
    summary: str
    gates: list[GateResult]
    receipts: list[ReceiptRef]
    artifacts: list[ArtifactRef]
    metrics: dict[str, Any]
    next_recommended: str | None
```

---

# 9. GateResult

```python
class GateResult(BaseModel):
    gate_id: str
    status: Literal["passed", "warning", "failed", "skipped"]
    severity: Literal["info", "warning", "error", "critical"]
    message: str
    evidence_refs: list[str]
    blocking: bool
```

---

# 10. Context Harness

## Purpose

Retrieve the minimum sufficient context.

## Responsibilities

- query KG first;
- retrieve memory only when relevant;
- create context envelope;
- enforce token budget;
- record omissions;
- preserve evidence references.

## Gates

- context_envelope_created
- token_budget_respected
- evidence_refs_present
- omissions_recorded
- no_broad_context_without_reason

## Outputs

- ContextEnvelope
- ContextRetrievalReceipt

---

# 11. Planning Harness

## Purpose

Ensure planning outputs are valid before mutation.

## Responsibilities

- validate task contract;
- validate acceptance criteria;
- detect missing constraints;
- detect scope creep;
- ensure no implementation code in planning.

## Gates

- task_contract_created
- acceptance_criteria_present
- constraints_recorded
- no_business_code_in_plan
- verification_strategy_present

---

# 12. Protocol Harness

## Purpose

Validate structured outputs from agents.

## Responsibilities

- parse XML/JSON/Markdown contracts;
- reject invalid output;
- extract typed artifacts;
- prevent freeform runtime input;
- normalize errors.

## Gates

- output_parseable
- schema_valid
- required_sections_present
- no_forbidden_fields
- runtime_contract_created

---

# 13. Mutation Harness

## Purpose

Apply code changes safely.

## Responsibilities

- enforce path policies;
- validate ApplyEdit operations;
- create checkpoint;
- apply patch;
- compute checksums;
- generate receipts;
- support rollback.

## Gates

- path_policy_passed
- checkpoint_created
- apply_edit_valid
- patch_created
- checksum_verified
- rollback_available

---

# 14. Inspection Harness

## Purpose

Verify changes locally before further LLM usage.

## Responsibilities

- syntax checks;
- AST guards;
- secret scan;
- lint;
- typecheck;
- targeted tests;
- broad tests when configured.

## Gates

- syntax_valid
- no_secret_leakage
- lint_passed_or_recorded
- typecheck_passed_or_recorded
- tests_passed_or_recorded
- srp_guard
- dip_guard

---

# 15. Diagnosis Harness

## Purpose

Repair recoverable failures methodically.

## Responsibilities

- reproduce failure;
- generate exactly three hypotheses;
- select hypothesis with evidence;
- instrument if needed;
- prevent repeated failed strategies;
- enforce attempt budget;
- trigger semantic compression.

## Gates

- reproduction_recorded
- hypothesis_count_valid
- selected_hypothesis_has_evidence
- failed_strategy_not_repeated
- attempt_budget_respected
- compression_applied_when_required

---

# 16. Review Harness

## Purpose

Perform grounded independent review.

## Responsibilities

- review changed scope;
- cite evidence;
- classify severity;
- detect correctness issues;
- detect maintainability issues;
- detect architecture regressions.

## Gates

- review_artifact_created
- findings_grounded
- severity_present
- no_unverified_claims
- changed_scope_respected

---

# 17. Security Harness

## Purpose

Protect sensitive surfaces.

## Responsibilities

- secret detection;
- auth/billing/API risk detection;
- trust boundary review;
- command/network risk review;
- provider exfiltration review.

## Gates

- no_secret_leakage
- trust_boundary_reviewed
- network_policy_passed
- no_high_risk_export
- security_findings_classified

---

# 18. Escalation Harness

## Purpose

Stop unsafe or non-convergent execution and produce a useful human handoff.

## Responsibilities

- detect exhausted attempts;
- resolve owners;
- package evidence;
- preserve patch state;
- create handoff;
- stop token burn.

## Gates

- escalation_reason_recorded
- owner_resolved_or_unknown_recorded
- handoff_created
- blocking_error_preserved
- next_action_present

---

# 19. Memory Harness

## Purpose

Promote useful knowledge into memory.

## Responsibilities

- extract memory candidates;
- classify memory;
- deduplicate;
- detect conflicts;
- reject noisy records;
- update project memory files.

## Gates

- memory_candidates_classified
- no_raw_cot_saved
- evidence_refs_present
- duplicates_checked
- stale_memory_marked

---

# 20. Knowledge Graph Harness

## Purpose

Keep the KG accurate after execution.

## Responsibilities

- incremental reindex;
- graph delta generation;
- changed symbol update;
- owner refresh;
- decision/failure edge update.

## Gates

- graph_delta_created
- changed_symbols_reindexed
- kg_consistency_checked
- owners_resolved_or_recorded_unknown

---

# 21. Consolidation Harness

## Purpose

Finalize execution.

## Responsibilities

- finalize artifacts;
- produce summary;
- purge L1 context;
- write memory delta;
- write graph delta;
- record cost/confidence.

## Gates

- summary_created
- artifacts_finalized
- receipts_finalized
- ephemeral_context_purged
- memory_delta_recorded
- graph_delta_recorded

---

# 22. Evaluation Harness

## Purpose

Measure runtime quality.

## Responsibilities

- run benchmarks;
- compare candidates;
- measure cost;
- measure success;
- record regressions;
- validate evolution proposals.

## Gates

- benchmark_result_created
- cost_recorded
- success_criteria_checked
- regression_checked

---

# 23. Harness Matrix

## SDD

| Harness | Default |
|---|---|
| Context | strict |
| Planning | strict |
| Protocol | warn |
| Mutation | strict |
| Inspection | warn/strict by profile |
| Diagnosis | optional |
| Review | strict |
| Security | conditional |
| Memory | strict |
| KG | strict |
| Consolidation | strict |
| Evaluation | warn |

## OC Flow

| Harness | Default |
|---|---|
| Context | strict |
| Planning | strict-lite |
| Protocol | strict |
| Mutation | strict |
| Inspection | strict |
| Diagnosis | strict |
| Review | optional |
| Security | conditional |
| Escalation | strict |
| Memory | strict |
| KG | strict |
| Consolidation | strict |
| Evaluation | warn |

---

# 24. Harness Events

Harnesses emit:

- harness.started
- harness.completed
- harness.failed
- gate.passed
- gate.warning
- gate.failed
- receipt.created
- artifact.created

---

# 25. Harness Receipts

Every harness that makes a meaningful decision creates receipts.

Examples:

- context retrieval receipt;
- mutation receipt;
- inspection receipt;
- diagnosis receipt;
- review receipt;
- security receipt;
- memory write receipt;
- graph update receipt.

---

# 26. Harness Configuration

```yaml
harnesses:
  context: strict
  planning: workflow_default
  protocol: workflow_default
  mutation: strict
  inspection: strict
  diagnosis: workflow_default
  review: workflow_default
  security: conditional
  escalation: strict
  memory: strict
  kg: strict
  consolidation: strict
  evaluation: warn
```

Profiles may override modes.

---

# 27. Plugin Harnesses

Plugins may add harnesses.

Requirements:

- manifest;
- version;
- required capabilities;
- gates;
- output schema;
- permission declaration;
- benchmark coverage.

Plugin harnesses cannot override core harnesses unless explicitly configured.

---

# 28. Migration from Current Branch

The current branch already has harness-like behaviour in:

- HarnessRunner
- phases
- gates
- verify logic
- apply logic
- memory provenance
- quality checks

Migration should:

1. Extract implicit checks into named harness definitions.
2. Keep existing behaviour.
3. Add HarnessRegistry.
4. Add HarnessResult.
5. Add GateResult.
6. Map SDD phases to harnesses.
7. Map OC Flow nodes to harnesses.
8. Add receipt generation.
9. Add benchmark coverage.

---

# 29. Invariants

1. Harnesses are not prompts.
2. Harnesses are reusable.
3. Harnesses are observable.
4. Harnesses are configurable.
5. Harnesses emit gate results.
6. Harnesses emit receipts for meaningful decisions.
7. Harnesses do not own workflow orchestration.
8. Harnesses do not bypass policy.
9. Harnesses are benchmarked.
10. Harnesses can be replaced through contracts.

---

# 30. Definition of Done

Harness Architecture is implemented when:

- HarnessRegistry exists.
- Core harnesses are defined.
- SDD uses harnesses declaratively.
- OC Flow uses harnesses declaratively.
- HarnessResult exists.
- GateResult exists.
- Harness events are emitted.
- Harness receipts are persisted.
- Profiles configure harness modes.
- Plugin harnesses can be loaded safely.
- Benchmarks measure harness performance.

---

# 31. Final Statement

Harnesses are the engineering discipline of OpenContext.

Agents may suggest.

Skills may perform.

Workflows may coordinate.

But harnesses decide whether the work is acceptable.
