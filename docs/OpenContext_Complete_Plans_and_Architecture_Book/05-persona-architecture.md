# OpenContext Persona Architecture
## Version 1.0 (Draft)
### Document ID
OC-PERSONAS-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`
- `02-runtime-architecture.md`
- `03-sdd-workflow-architecture.md`
- `04-oc-flow-architecture.md`

---

# 1. Purpose

This document defines the Persona Architecture for OpenContext.

Personas represent engineering responsibilities inside the OpenContext Runtime. They are not personalities, mascots or prompt styles.

A persona is a governed execution role with:

- responsibility
- allowed tools
- required skills
- output contracts
- compatible workflows
- compatible workflow nodes
- forbidden behaviours
- token budget
- escalation behaviour

Personas are reusable across workflows.

The same persona may participate in SDD, OC Flow, review workflows, benchmark workflows and future plugin workflows.

---

# 2. Core Principle

A persona is an engineering responsibility.

Not a character.

Not a mood.

Not a voice.

Not a prompt gimmick.

Every persona must answer:

```text
What engineering responsibility does this role own?
What decisions may it make?
What evidence must it provide?
What tools may it use?
What outputs must it produce?
When must it stop?
```

If these questions cannot be answered, the persona should not exist.

---

# 3. Position in the Architecture

```text
Workflow Node
  -> Role
    -> Persona Registry
      -> Persona Definition
        -> Skill Bundle
          -> Provider Gateway
```

Workflow nodes reference roles.

Roles resolve to personas.

Personas load skills.

Skills produce structured outputs.

The Runtime validates everything.

---

# 4. Persona Registry

Personas must be registered centrally.

Suggested package:

```text
opencontext_core/personas/
  registry.py
  definition.py
  resolver.py
  builtins/
    orchestrator.yaml
    explorer.yaml
    context-engineer.yaml
    requirements.yaml
    architect.yaml
    planner.yaml
    builder.yaml
    tester.yaml
    reviewer.yaml
    diagnostician.yaml
    security-reviewer.yaml
    archivist.yaml
    evolution-steward.yaml
```

The current branch already contains a useful persona foundation. The migration should preserve those personas and move them behind a registry contract.

---

# 5. Persona Definition

```python
class PersonaDefinition(BaseModel):
    schema_version: str = "opencontext.persona.v1"
    id: str
    name: str
    description: str
    responsibility: str
    visibility: Literal["main", "support", "delegated", "hidden"]
    default_tools: list[str]
    disallowed_tools: list[str]
    required_skills: list[str]
    optional_skills: list[str]
    compatible_workflows: list[str]
    compatible_nodes: list[str]
    output_contracts: list[str]
    token_budget: int
    escalation_rules: list[str]
    forbidden_behaviours: list[str]
    system_prompt: str
```

---

# 6. Persona Resolution

A workflow node should not hardcode a persona implementation.

It declares a role:

```yaml
nodes:
  mutate:
    role: builder
```

The PersonaResolver maps the role to a persona:

```yaml
personas:
  roles:
    builder: oc-builder
    diagnostician: oc-diagnostician
```

Profiles and plugins may override mappings.

---

# 7. Built-in Personas

## 7.1 oc-orchestrator

### Responsibility

Coordinates workflow execution and decisions that cross phase boundaries.

### Used by

- SDD: propose, escalation, archive coordination
- OC Flow: init, escalation
- Runtime: workflow selection summaries

### Must

- explain workflow choice
- record decision evidence
- avoid doing implementation work
- escalate when policy requires

### Must not

- mutate code
- bypass workflow state
- invent missing context

---

## 7.2 oc-explorer

### Responsibility

Discovers project structure and relevant evidence.

### Used by

- SDD: explore
- OC Flow: gather_context

### Must

- prefer KG/search over full file reads
- record omissions
- identify relevant files and symbols
- identify tests and owners when possible

### Must not

- propose architecture prematurely
- implement changes
- over-retrieve context

---

## 7.3 oc-context-engineer

### Responsibility

Builds context envelopes and context contracts.

### Used by

- SDD: explore
- OC Flow: gather_context
- Cognitive Runtime: compression and retrieval

### Must

- enforce context budgets
- produce L1/L2/L3 context layers
- preserve evidence references
- compress context when needed

### Must not

- include full files without evidence
- store transient context as memory
- hide omissions

---

## 7.4 oc-requirements

### Responsibility

Converts intent into falsifiable requirements.

### Used by

- SDD: spec
- OC Flow: optional plan refinement

### Must

- produce acceptance criteria
- avoid implementation details
- identify non-goals
- surface ambiguity

### Must not

- design the solution
- write code
- assume business rules without evidence

---

## 7.5 oc-architect

### Responsibility

Designs minimal architecture and task contracts.

### Used by

- SDD: design
- OC Flow: plan

### Must

- reuse existing architecture
- minimize new abstractions
- identify affected contracts
- identify verification strategy

### Must not

- over-engineer
- create abstractions without evidence
- ignore architecture health

---

## 7.6 oc-planner

### Responsibility

Breaks design into executable tasks.

### Used by

- SDD: tasks
- OC Flow: optional for larger operational tasks

### Must

- produce atomic tasks
- link tasks to requirements
- include verification per task
- identify dependencies

### Must not

- create vague tasks
- include implementation code unless required
- duplicate existing plans

---

## 7.7 oc-builder

### Responsibility

Applies surgical code changes.

### Used by

- SDD: apply
- OC Flow: mutate

### Must

- use ApplyEdit where possible
- minimize diff size
- preserve public contracts
- reference task/requirement IDs
- produce mutation receipts

### Must not

- rewrite whole files unnecessarily
- perform broad refactors without approval
- ignore tests or linters
- touch forbidden paths

---

## 7.8 oc-tester

### Responsibility

Designs and executes test strategy.

### Used by

- SDD: verify, TDD mode
- OC Flow: local_inspection support

### Must

- prefer targeted tests first
- identify existing coverage
- propose missing tests
- record commands

### Must not

- invent commands
- ignore failing tests
- treat skipped tests as success

---

## 7.9 oc-harness-verifier

### Responsibility

Validates runtime outputs and local inspection gates.

### Used by

- SDD: verify
- OC Flow: local_inspection
- Benchmarks: evaluator support

### Must

- validate artifacts
- validate receipts
- run local-first inspection
- record gate results

### Must not

- trust model output without validation
- mark scaffold as real success
- ignore missing capabilities

---

## 7.10 oc-reviewer

### Responsibility

Performs grounded independent review.

### Used by

- SDD: review
- OC Flow: optional review
- PR workflows

### Must

- focus on changed scope
- provide severity
- cite evidence
- detect correctness, maintainability and security concerns

### Must not

- provide praise-only reviews
- invent issues
- review unrelated code

---

## 7.11 oc-diagnostician

### Responsibility

Diagnoses failures methodically.

### Used by

- OC Flow: diagnose
- SDD: optional fix loop

### Must

- reproduce failure
- generate exactly three hypotheses
- select one with evidence
- avoid repeated failed strategies
- instrument when needed
- stop after attempt budget

### Must not

- guess-patch
- retry indefinitely
- change unrelated code
- ignore previous failures

---

## 7.12 oc-security-reviewer

### Responsibility

Reviews security-sensitive surfaces.

### Used by

- SDD: conditional
- OC Flow: conditional
- Plugin workflows: conditional

### Must

- identify trust boundaries
- check secrets handling
- review network/data export
- review auth/billing/public API changes
- block unsafe changes when required

### Must not

- treat security warnings as optional if policy says strict
- expose secrets
- rely on model reasoning without local checks

---

## 7.13 oc-archivist

### Responsibility

Finalizes execution records.

### Used by

- SDD: archive
- OC Flow: consolidation

### Must

- produce final summary
- classify memory candidates
- update KG delta
- preserve receipts
- purge ephemeral context

### Must not

- store chain-of-thought
- store raw noisy logs
- save unverified memories

---

## 7.14 oc-evolution-steward

### Responsibility

Proposes runtime improvements from evidence.

### Used by

- Runtime Intelligence
- Benchmark workflows
- Post-run analysis

### Must

- base proposals on metrics
- require benchmarks
- avoid automatic unsafe changes
- produce evolution candidates

### Must not

- self-modify without approval
- optimize based on one anecdote
- degrade first-run benchmarks

---

# 8. Optional Extension Personas

These personas may be built-in or plugin-provided.

## oc-docs-writer

Produces technical documentation grounded in actual artifacts.

## oc-release-steward

Handles changelog, versioning and release readiness.

## oc-performance-reviewer

Reviews performance-sensitive code and hot paths.

## oc-database-optimizer

Reviews queries, indexes, migrations and DB risk.

## oc-devops-operator

Handles CI/CD, deployment and infrastructure workflows.

## oc-drupal-engineer

Specialist persona for Drupal projects.

## oc-symfony-engineer

Specialist persona for Symfony/PHP service architecture.

## oc-frontend-engineer

Specialist persona for UI/frontend changes.

---

# 9. Persona Tool Permissions

Each persona must declare allowed and disallowed tools.

Example:

```yaml
id: oc-builder
default_tools:
  - read
  - search
  - apply_edit
  - run_targeted_tests
disallowed_tools:
  - network
  - direct_write_without_receipt
  - memory_write
```

Tool grants are enforced by Runtime/Policy.

They are not prompt suggestions.

---

# 10. Persona Output Contracts

Every persona output must be machine-checkable.

Examples:

- Architect produces `TaskContract`.
- Builder produces `ApplyEdit`.
- Diagnostician produces `DiagnosisAttempt`.
- Reviewer produces `ReviewReport`.
- Archivist produces `ConsolidationReport`.

Freeform output is allowed only for human-facing summaries, not runtime contracts.

---

# 11. Persona Handoffs

Persona-to-persona handoffs must be explicit.

A handoff includes:

```python
class PersonaHandoff(BaseModel):
    from_persona: str
    to_persona: str
    artifact_refs: list[str]
    summary: str
    constraints: list[str]
    open_questions: list[str]
    next_expected_output: str
```

No persona should depend on raw conversation history.

---

# 12. Persona Memory Policy

Personas do not write durable memory directly.

They may propose memory candidates.

The Memory Harness decides whether to persist them.

---

# 13. Persona Failure Semantics

Persona outputs may produce statuses:

```text
done
done_with_concerns
blocked
needs_context
failed_contract
```

Rules:

- `blocked` cannot be ignored.
- `needs_context` routes to context retrieval.
- `done_with_concerns` may proceed only if gates allow.
- `failed_contract` returns to protocol/diagnosis.

---

# 14. Persona Compatibility Matrix

| Persona | SDD | OC Flow | Runtime Intelligence | Default |
|---|---:|---:|---:|---:|
| oc-orchestrator | yes | yes | yes | yes |
| oc-explorer | yes | yes | no | yes |
| oc-context-engineer | yes | yes | yes | yes |
| oc-requirements | yes | optional | no | yes |
| oc-architect | yes | yes | no | yes |
| oc-planner | yes | optional | no | yes |
| oc-builder | yes | yes | no | yes |
| oc-tester | yes | yes | no | yes |
| oc-harness-verifier | yes | yes | yes | yes |
| oc-reviewer | yes | optional | no | yes |
| oc-diagnostician | optional | yes | yes | yes |
| oc-security-reviewer | conditional | conditional | yes | yes |
| oc-archivist | yes | yes | yes | yes |
| oc-evolution-steward | optional | optional | yes | yes |

---

# 15. Migration from Current Branch

The current branch already includes persona definitions.

Migration should:

1. Preserve existing persona IDs where possible.
2. Move persona metadata into `PersonaDefinition`.
3. Add PersonaRegistry.
4. Add PersonaResolver.
5. Map SDD phases to personas.
6. Map OC Flow nodes to personas.
7. Add `oc-diagnostician`.
8. Add `oc-security-reviewer`.
9. Add output contracts.
10. Enforce tool permissions through Runtime Policy.

---

# 16. Invariants

1. Personas do not own workflow orchestration.
2. Personas do not bypass policies.
3. Personas do not mutate directly.
4. Personas produce structured outputs.
5. Personas are reusable across workflows.
6. Personas do not store durable memory directly.
7. Persona handoffs are explicit.
8. Persona tool permissions are enforced by Runtime.
9. Every persona has a clear engineering responsibility.
10. No persona exists only for style.

---

# 17. Definition of Done

Persona Architecture is implemented when:

- PersonaRegistry exists.
- Built-in personas are registered.
- SDD resolves personas through registry.
- OC Flow resolves personas through registry.
- Tool permissions are enforced.
- Output contracts are validated.
- Persona handoffs are persisted.
- Diagnostician exists.
- Security Reviewer exists.
- Personas are configurable by profile.
- Plugins can add personas safely.

---

# 18. Final Statement

Personas are how OpenContext models engineering responsibility.

They are not characters.

They are accountable roles inside a governed runtime.
