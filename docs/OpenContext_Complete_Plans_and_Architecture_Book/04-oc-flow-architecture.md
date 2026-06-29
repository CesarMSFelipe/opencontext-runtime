# OC Flow Architecture
## Version 1.0 (Draft)
### Document ID
OC-OCFLOW-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `02-runtime-architecture.md`
- `03-sdd-workflow-architecture.md`

---

# 1. Purpose

This document defines OC Flow as a first-class operational workflow executed by the OpenContext Runtime.

OC Flow is the fast, local-first, agentic workflow for focused engineering tasks. It is designed for the first successful user experience after installation: small enough to be efficient, structured enough to be safe, and observable enough to be trusted.

OC Flow does not replace SDD.

OC Flow coexists with SDD and shares the same Runtime, Knowledge Graph, Memory, Context Engineering, Harnesses, Personas, Skills, Policies, Capabilities, Events, Artifacts and Receipts.

---

# 2. Mission

OC Flow exists to complete practical engineering tasks with low uncertainty and low token cost.

Its mission is:

```text
Understand the task
↓
Retrieve minimal context
↓
Plan briefly
↓
Mutate surgically
↓
Inspect locally
↓
Diagnose methodically if needed
↓
Consolidate useful knowledge
```

OC Flow should feel like a disciplined senior engineer making one focused change, not like an unconstrained autonomous coding agent.

---

# 3. Recommended Use Cases

OC Flow should be selected for:

- failing tests
- localized bug fixes
- lint/type errors
- small refactors
- one-module improvements
- maintenance tasks
- small documentation updates
- incremental runtime improvements
- safe dependency or configuration fixes

OC Flow should not be the default for:

- large features
- architecture redesigns
- public API changes
- schema migrations
- broad multi-package changes
- high-risk security-sensitive changes

Those should generally use SDD.

---

# 4. Canonical Flow

```text
init
  -> gather_context
  -> plan
  -> mutate
  -> local_inspection
      -> consolidation        if passed
      -> diagnose             if recoverable failure
      -> escalation           if blocked

diagnose
  -> mutate                   if fix ready
  -> escalation               if attempts exhausted

escalation
  -> consolidation

consolidation
  -> completed
```

---

# 5. Runtime Integration

OC Flow is executed by the shared Runtime.

The Runtime owns:

- session lifecycle
- workflow selection
- state transitions
- event emission
- policy enforcement
- artifact persistence
- receipts
- checkpoints
- resume
- consolidation

OC Flow owns only its workflow definition and node semantics.

It must never bypass Runtime governance.

---

# 6. Workflow Definition

OC Flow must be represented as a declarative workflow.

```yaml
schema_version: opencontext.workflow.v1
id: oc-flow
label: OpenContext Agentic Flow
kind: operational
version: "1.0"
start_node: init
terminal_nodes:
  - completed

nodes:
  init:
    role: orchestrator
    action: session_init

  gather_context:
    role: context_engineer
    action: gather_context_layers

  plan:
    role: architect
    action: produce_task_contract

  mutate:
    role: builder
    action: apply_structured_mutation

  local_inspection:
    role: harness_verifier
    action: inspect_changed_scope

  diagnose:
    role: diagnostician
    action: diagnosis_loop

  escalation:
    role: orchestrator
    action: escalate_to_owner

  consolidation:
    role: archivist
    action: consolidate_session

  completed:
    role: runtime
    action: complete

edges:
  - from_node: init
    to_node: gather_context
  - from_node: gather_context
    to_node: plan
  - from_node: plan
    to_node: mutate
  - from_node: mutate
    to_node: local_inspection
  - from_node: local_inspection
    to_node: consolidation
    condition: inspection_passed
  - from_node: local_inspection
    to_node: diagnose
    condition: inspection_failed_recoverable
  - from_node: local_inspection
    to_node: escalation
    condition: inspection_failed_blocking
  - from_node: diagnose
    to_node: mutate
    condition: fix_ready
  - from_node: diagnose
    to_node: escalation
    condition: attempts_exhausted
  - from_node: escalation
    to_node: consolidation
  - from_node: consolidation
    to_node: completed
```

---

# 7. Node: init

## Purpose

Initialize the session, bind task, profile, policy, capabilities and workflow definition.

## Inputs

- user task
- repository root
- profile
- workflow selection receipt
- config snapshot
- capability scan

## Outputs

- session record
- run record
- live state
- init event
- workflow selection receipt

## Required Harnesses

- policy bootstrap
- capability bootstrap
- session bootstrap
- dirty worktree warning
- config validation

## Exit Conditions

`init` may transition to `gather_context` only when:

- session exists;
- workflow definition is loaded;
- config snapshot is persisted;
- capabilities are available;
- policy mode is known.

---

# 8. Node: gather_context

## Purpose

Retrieve the minimum sufficient context for the task.

## Inputs

- task
- workflow definition
- KG
- memory
- project profile
- active plans/sessions

## Outputs

- L3 subgraph
- L3 signatures
- L2 seed contract
- L1 focus context
- context envelope
- omissions list
- context retrieval receipt

## Required Harnesses

- Context Harness
- KG Harness
- Memory Harness
- Compression Harness

## Rules

- KG first.
- Memory second.
- Files only when needed.
- Full files require evidence or explicit policy.
- Every omission must be recorded if relevant.
- Context budget must be enforced.

## Exit Conditions

`gather_context` may transition to `plan` only when:

- context envelope exists;
- token budget is respected;
- relevant evidence sources are recorded;
- missing context is either resolved or explicitly marked.

---

# 9. Node: plan

## Purpose

Create a short immutable task contract.

OC Flow planning is intentionally lighter than SDD.

It should not produce a full formal specification unless the workflow selector recommends switching to SDD.

## Inputs

- context envelope
- task
- relevant memory
- policies
- risk flags

## Outputs

- task contract
- acceptance criteria
- constraints
- affected files/symbols
- required verification
- plan receipt

## Required Harnesses

- Planning Harness
- Policy Harness
- Protocol Harness

## Output Contract

The plan must define:

- scope
- non-scope
- acceptance criteria
- constraints
- changed areas
- verification plan
- risk flags
- stop conditions

## Rules

- No business code in plan.
- No speculative architecture.
- Prefer existing code.
- Keep plan short.
- Switch to SDD if scope grows.

## Exit Conditions

`plan` may transition to `mutate` only when:

- task contract is frozen;
- acceptance criteria exist;
- verification strategy exists;
- risk is acceptable for OC Flow.

---

# 10. Node: mutate

## Purpose

Apply a minimal surgical change.

## Inputs

- frozen task contract
- L1 focused context
- relevant code snippets
- verification plan
- policy decisions

## Outputs

- mutation proposal
- ApplyEdit operations
- patch
- apply receipts
- checkpoint
- mutation event

## Required Harnesses

- Mutation Harness
- Policy Harness
- Security Harness
- Receipt Harness

## Rules

- ApplyEdit first.
- Whole-file rewrite only by exception.
- Every mutation requires a reason.
- Every mutation references an acceptance criterion.
- Every mutation must be checkpointed.
- Forbidden paths are blocked before writing.

## Exit Conditions

`mutate` may transition to `local_inspection` only when:

- all edits applied successfully;
- receipts exist;
- patch exists;
- rollback checkpoint exists;
- policy allowed the change.

---

# 11. Node: local_inspection

## Purpose

Verify the change locally before spending additional tokens.

## Inputs

- patch
- apply receipts
- task contract
- capability set
- test/lint commands
- changed files

## Outputs

- inspection report
- gate results
- test/lint output
- failure summary if failed
- inspection receipt

## Required Harnesses

- Inspection Harness
- Security Harness
- AST Harness
- Test Harness
- Policy Harness

## Inspection Order

```text
protocol validation
path validation
syntax
AST guards
secret scan
lint
typecheck
targeted tests
broad tests if configured
quality gates
```

## Outcomes

```text
passed
failed_recoverable
failed_blocking
skipped_with_reason
```

## Exit Conditions

- `passed` -> `consolidation`
- `failed_recoverable` -> `diagnose`
- `failed_blocking` -> `escalation`

---

# 12. Node: diagnose

## Purpose

Repair recoverable failures methodically.

OC Flow diagnosis is bounded and evidence-driven.

## Inputs

- failed inspection report
- current patch
- task contract
- previous attempts
- compressed failure context
- relevant memory

## Outputs

- diagnosis attempt
- reproduction command/result
- exactly three hypotheses
- selected hypothesis
- evidence
- fix strategy
- optional mutation proposal
- diagnosis receipt

## Required Harnesses

- Diagnosis Harness
- Compression Harness
- Memory Harness
- Policy Harness

## Diagnosis Method

```text
REPRODUCE
↓
HYPOTHESIZE exactly 3
↓
SELECT with evidence
↓
INSTRUMENT if needed
↓
FIX
↓
RECHECK
```

## Rules

- Maximum attempts are profile-controlled.
- Default balanced profile: 2 attempts.
- Enterprise profile: 3 attempts.
- Never repeat a failed strategy.
- Compress after repeated failures.
- Stop if confidence drops below threshold.

## Exit Conditions

- `fix_ready` -> `mutate`
- `needs_context` -> `gather_context`
- `attempts_exhausted` -> `escalation`
- `policy_blocked` -> `escalation`

---

# 13. Node: escalation

## Purpose

Stop token burn and produce a useful human handoff when the runtime cannot safely converge.

## Inputs

- task contract
- failed attempts
- blocking error
- patch state
- affected files/symbols
- owner data
- policy decisions

## Outputs

- escalation report
- handoff document
- owner candidates
- current patch
- known blockers
- next recommended action

## Required Harnesses

- Escalation Harness
- KG Owner Harness
- Memory Harness
- Policy Harness

## Rules

- Escalation is valid.
- Escalation is not silent failure.
- Escalation must preserve evidence.
- Escalation must not continue code generation.

## Exit Conditions

`escalation` transitions to `consolidation` after the handoff is persisted.

---

# 14. Node: consolidation

## Purpose

Finalize the session.

## Inputs

- all artifacts
- receipts
- events
- inspection reports
- diagnosis attempts
- escalation report if any
- memory candidates
- KG deltas

## Outputs

- final summary
- memory delta
- graph delta
- archived L1 context
- cost report
- confidence report
- run status

## Required Harnesses

- Consolidation Harness
- Memory Harness
- KG Harness
- Compression Harness
- Runtime Intelligence Harness

## Rules

- Save durable knowledge only.
- Do not save chain-of-thought.
- Purge ephemeral context after success.
- Preserve evidence for auditability.
- Reindex changed files.
- Record token/cost savings.

## Exit Conditions

`consolidation` transitions to `completed`.

---

# 15. Personas

OC Flow uses the shared Persona Registry.

Default mapping:

| Node | Persona |
|---|---|
| init | oc-orchestrator |
| gather_context | oc-context-engineer |
| plan | oc-architect |
| mutate | oc-builder |
| local_inspection | oc-harness-verifier |
| diagnose | oc-diagnostician |
| escalation | oc-orchestrator |
| consolidation | oc-archivist |

Personas are not unique to OC Flow.

They are reused by SDD and other workflows.

---

# 16. Skills

Default OC Flow skill bundle:

```yaml
oc_flow_default:
  - oc-intent-clarify
  - oc-context-discovery
  - oc-plan-discovery
  - oc-review-situation
  - oc-strategy-compare
  - oc-plan-lite
  - oc-apply-surgical
  - oc-inspect-local-first
  - oc-diagnose-three-hypotheses
  - oc-semantic-gc
  - oc-escalate-owner
  - oc-archive-memory
```

Only relevant skills should be loaded per node.

---

# 17. Harness Matrix

| Harness | Mode |
|---|---|
| Context | strict |
| Planning | strict-lite |
| Protocol | strict |
| Mutation | strict |
| Inspection | strict |
| Diagnosis | strict |
| Security | conditional |
| Escalation | strict |
| Memory | strict |
| KG | strict |
| Consolidation | strict |

---

# 18. Context Strategy

OC Flow uses surgical-first context retrieval.

Default order:

```text
KG exact match
↓
symbol signatures
↓
related tests
↓
owners
↓
recent failure memory
↓
small snippets
↓
full files only if required
```

Broad context retrieval is forbidden by default.

---

# 19. Token Budget

OC Flow default budgets:

| Node | Target |
|---|---:|
| gather_context | 2k-4.5k |
| plan | 1k-2k |
| mutate | 1.5k-3k |
| local_inspection | 0 LLM |
| diagnose | 2k-4k per attempt |
| consolidation | 0-1k |

Balanced target for a first bugfix:

```text
< 7k-10k total tokens
```

---

# 20. Runtime Modes

OC Flow supports:

- run_to_completion
- interactive
- step
- dry_run
- simulate
- resume

First-run default:

```text
run_to_completion
```

unless approval is required.

---

# 21. Failure Semantics

OC Flow failures must be typed.

```text
context_missing
plan_invalid
policy_denied
mutation_failed
inspection_failed
diagnosis_exhausted
owner_required
confidence_too_low
```

Every failure must include:

- recoverability
- evidence
- next action
- user-facing summary

---

# 22. Resume Semantics

OC Flow resume must restore:

- task contract
- context envelope
- patch state
- receipts
- inspection reports
- diagnosis attempts
- failure compressor output
- live state

If any required artifact is missing, resume must fail safely.

---

# 23. Relationship with SDD

OC Flow may switch to SDD when:

- scope expands;
- confidence drops;
- blast radius increases;
- public API is affected;
- architecture changes become necessary;
- policy requires formal workflow.

Switching workflow requires a receipt.

---

# 24. Configuration

```yaml
workflow:
  oc-flow:
    enabled: true
    default_lane: fast

oc_flow:
  max_attempts: 2
  context_strategy: surgical_first
  protocol: xml
  local_first: true
  auto_switch_to_sdd: true
  review:
    enabled: optional
  escalation:
    enabled: true
```

---

# 25. First-Run Requirement

A clean install must support:

```bash
opencontext run "Fix failing test" --workflow oc-flow
```

Expected result:

- workflow selected;
- context retrieved surgically;
- task contract generated;
- small patch applied;
- tests/lint run if available;
- diagnosis if needed;
- summary produced;
- artifacts persisted.

---

# 26. Artifacts

OC Flow artifact layout:

```text
.opencontext/sessions/<session_id>/runs/<run_id>/artifacts/oc-flow/
  context-envelope.json
  task-contract.json
  mutation-001.xml
  patch.diff
  apply-receipts.json
  inspection-report.json
  diagnosis/
    attempt-001.json
    attempt-002.json
    compressed-failure-context.md
  escalation/
    escalation-report.json
    handoff.md
  consolidation/
    memory-delta.json
    graph-delta.json
    summary.md
```

---

# 27. Events

OC Flow emits:

- workflow.selected
- node.started
- node.completed
- context.retrieved
- contract.created
- mutation.proposed
- mutation.applied
- inspection.completed
- diagnosis.started
- diagnosis.attempted
- escalation.created
- consolidation.completed
- workflow.completed

---

# 28. Definition of Done

OC Flow is implemented when:

- workflow definition exists;
- Runtime executes all nodes;
- context retrieval is surgical;
- task contract is persisted;
- mutation uses ApplyEdit;
- receipts are produced;
- local inspection works;
- diagnosis loop works;
- escalation works;
- consolidation updates KG and memory;
- first-run bugfix benchmark passes;
- MCP and CLI expose OC Flow;
- Studio can render live state.

---

# 29. Final Statement

OC Flow is the operational heartbeat of OpenContext.

SDD makes OpenContext deliberate.

OC Flow makes OpenContext practical.

Together they make the runtime useful on the first day and trustworthy over the long term.
