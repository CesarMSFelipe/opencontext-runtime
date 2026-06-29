# OpenContext Runtime Architecture
## Version 1.0 (Draft)
### Document ID
OC-RUNTIME-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`
- `01-system-architecture.md`

---

# 1. Purpose

This document defines the architecture of the OpenContext Runtime.

The Runtime is the execution core of OpenContext. It creates sessions, selects workflows, executes workflow graphs, coordinates harnesses, enforces policies, emits events, persists artifacts and returns explainable results.

The Runtime must remain workflow-neutral.

It must support both:

- **SDD Workflow**
- **OC Flow**

without embedding either methodology directly into the core execution engine.

---

# 2. Runtime Mission

The Runtime exists to coordinate engineering work under governance.

It does not exist to maximise autonomy.

It exists to reduce uncertainty through:

- deterministic state management
- controlled workflow execution
- explicit context retrieval
- policy enforcement
- artifact persistence
- receipts
- validation
- observability
- resume
- consolidation

The Runtime is responsible for ensuring that no workflow becomes an opaque agent loop.

---

# 3. Core Responsibilities

The Runtime owns:

1. Session lifecycle.
2. Workflow selection.
3. Workflow execution.
4. State transitions.
5. Harness orchestration.
6. Policy enforcement.
7. Event emission.
8. Artifact persistence.
9. Receipt generation.
10. Checkpoint and rollback.
11. Resume.
12. Summary generation.
13. Consolidation.
14. Escalation.
15. Runtime metrics.

The Runtime does not own:

- workflow semantics;
- persona prompts;
- skill logic;
- KG implementation;
- memory implementation;
- provider-specific model logic;
- UI rendering.

---

# 4. Runtime Position in the System

```text
Interfaces
  -> Runtime API
      -> Session Runtime
      -> Workflow Engine
      -> State Machine
      -> Harness Registry
      -> Policy Engine
      -> Event Bus
      -> Artifact Store
      -> Receipt Store
      -> KG / Memory / Context
      -> Provider Gateway
```

All external entrypoints must go through the Runtime API.

No interface may directly execute a phase, mutate files, write memory or bypass policies.

---

# 5. Runtime Components

```text
runtime/
  api.py
  session.py
  session_store.py
  orchestrator.py
  workflow_runner.py
  state_machine.py
  events.py
  event_bus.py
  artifacts.py
  receipts.py
  checkpoints.py
  summaries.py
  escalation.py
  consolidation.py
  telemetry.py
  errors.py
```

---

# 6. Runtime API

The Runtime API is the stable boundary used by MCP, CLI, TUI, Studio and IDE adapters.

```python
class RuntimeApi:
    def start_session(self, request: StartSessionRequest) -> SessionRef: ...
    def run(self, request: RunRequest) -> RunResult: ...
    def next(self, session_id: str) -> NextAction: ...
    def observe(self, session_id: str, event: RuntimeEventInput) -> SessionState: ...
    def apply(self, session_id: str, mutation: MutationRequest) -> ApplyResult: ...
    def inspect(self, session_id: str, scope: InspectionScope) -> InspectionReport: ...
    def resume(self, session_id: str) -> SessionState: ...
    def archive(self, session_id: str) -> ArchiveResult: ...
    def status(self, session_id: str) -> SessionStatus: ...
```

The existing `opencontext_run` MCP tool should eventually call `RuntimeApi.run()`.

---

# 7. Session Runtime

## 7.1 Session

A Session is the top-level container for a user task.

A Session may contain multiple workflow runs.

Example:

```text
Session
  Run 1: sdd
  Run 2: oc-flow
  Run 3: review
```

## 7.2 RuntimeSession Model

```python
class RuntimeSession(BaseModel):
    schema_version: str = "opencontext.session.v1"
    session_id: str
    root: str
    task: str
    profile: str
    status: str
    active_run_id: str | None
    context_id: str | None
    config_snapshot: dict[str, Any]
    capabilities: dict[str, bool]
    created_at: str
    updated_at: str
    live_state_path: str
    events_path: str
    artifacts_root: str
```

## 7.3 Session Statuses

```text
created
running
waiting_for_approval
paused
completed
failed
escalated
archived
```

---

# 8. Run

A Run is one execution of one workflow inside a Session.

```python
class RuntimeRun(BaseModel):
    schema_version: str = "opencontext.run.v1"
    run_id: str
    session_id: str
    workflow_id: str
    status: str
    current_node: str | None
    started_at: str
    completed_at: str | None
    artifacts: list[ArtifactRef]
    receipts: list[ReceiptRef]
    events: list[str]
```

A run must not exist outside a session.

For backward compatibility, legacy run folders may be preserved.

---

# 9. Workflow Execution

The Runtime executes a `WorkflowDefinition`.

A workflow is a graph.

A graph contains:

- nodes;
- edges;
- roles;
- required skills;
- required harnesses;
- gates;
- retry policies;
- output contracts.

The Runtime does not hardcode workflow nodes.

---

# 10. State Machine

## 10.1 Runtime State Machine

The State Machine validates transitions between workflow nodes.

It is generic.

It receives:

```python
current_node
target_node
workflow_definition
transition_condition
runtime_context
```

It returns:

```python
TransitionDecision
```

## 10.2 TransitionDecision

```python
class TransitionDecision(BaseModel):
    allowed: bool
    reason: str
    required_gates: list[str]
    failed_gates: list[str]
    next_node: str | None
```

No transition should occur without a `TransitionDecision`.

---

# 11. Workflow Runner

The Workflow Runner is responsible for executing one workflow run.

```python
class WorkflowRunner:
    def run_to_completion(self, run_id: str) -> RunResult: ...
    def step(self, run_id: str) -> NextAction: ...
    def execute_node(self, run_id: str, node_id: str) -> NodeResult: ...
```

It delegates:

- context retrieval to Context Harness;
- model work to Persona/Skill/Provider layer;
- mutation to Mutation Harness;
- verification to Inspection Harness;
- policy decisions to Policy Engine;
- persistence to Artifact Store.

---

# 12. Node Execution

Each workflow node executes through a standard pipeline.

```text
load session
load workflow
load node definition
check capabilities
evaluate policies
prepare context
load persona
load skills
execute harness pre-checks
execute node action
validate output contract
persist artifacts
emit receipts
execute harness post-checks
transition
```

---

# 13. NodeResult

```python
class NodeResult(BaseModel):
    schema_version: str = "opencontext.node_result.v1"
    session_id: str
    run_id: str
    workflow_id: str
    node_id: str
    status: str
    summary: str
    artifacts: list[ArtifactRef]
    receipts: list[ReceiptRef]
    gates: list[GateResult]
    token_usage: dict[str, int]
    duration_ms: int
    next_recommended: str | None
    error: str | None
```

---

# 14. Relationship with Existing HarnessRunner

The current branch already contains `HarnessRunner`.

It should not be deleted immediately.

Migration path:

1. Keep `HarnessRunner.run()` for compatibility.
2. Add RuntimeSession creation around current runs.
3. Emit RuntimeEvents from current phase execution.
4. Add WorkflowRegistry.
5. Register SDD as a WorkflowDefinition.
6. Make `HarnessRunner.run()` delegate to `WorkflowRunner`.
7. Keep legacy return shapes until callers migrate.

---

# 15. Backward Compatibility

Existing usage must continue to work:

```text
opencontext_run
workflow=sdd
workflow=standard
workflow=quick
```

The compatibility layer must map legacy workflow names to workflow definitions.

```text
full      -> sdd
standard  -> sdd-standard profile
quick     -> sdd-quick profile
```

---

# 16. Runtime Events

Every significant action emits an event.

Events are append-only.

```python
class RuntimeEvent(BaseModel):
    schema_version: str = "opencontext.runtime_event.v1"
    event_id: str
    session_id: str
    run_id: str | None
    workflow_id: str | None
    node_id: str | None
    type: str
    status: str
    message: str
    metadata: dict[str, Any]
    created_at: str
```

Required event categories:

- session
- workflow
- node
- harness
- policy
- context
- memory
- KG
- skill
- persona
- provider
- mutation
- inspection
- diagnosis
- escalation
- consolidation

---

# 17. Event Bus

The Event Bus is the runtime's observability backbone.

```python
class EventBus:
    def publish(self, event: RuntimeEvent) -> None: ...
    def subscribe(self, consumer: EventConsumer) -> None: ...
```

Default implementation:

```text
JSONL event stream
```

Optional implementations:

- OpenTelemetry exporter;
- Studio stream;
- stdout stream;
- test collector.

---

# 18. Live State

Every active session writes a live state file.

```json
{
  "session_id": "...",
  "run_id": "...",
  "workflow": "oc-flow",
  "node": "diagnose",
  "status": "running",
  "message": "Diagnosing failed test: hypothesis 2 of 3",
  "attempt": 2,
  "max_attempts": 3,
  "last_event_id": "..."
}
```

This file powers:

- CLI status;
- TUI;
- Studio;
- MCP status output.

---

# 19. Artifacts

Artifacts are durable outputs.

The Runtime owns artifact registration.

Artifact examples:

- specs;
- designs;
- task contracts;
- context envelopes;
- patches;
- receipts;
- inspection reports;
- diagnosis reports;
- summaries;
- escalation reports;
- memory deltas;
- graph deltas.

```python
class ArtifactRef(BaseModel):
    artifact_id: str
    session_id: str
    run_id: str
    kind: str
    path: str
    produced_by: str
    created_at: str
    checksum: str | None
```

No major output should exist only in chat.

---

# 20. Receipts

Receipts prove that an action happened.

Receipt examples:

- workflow selection receipt;
- context retrieval receipt;
- mutation receipt;
- policy decision receipt;
- inspection receipt;
- memory write receipt;
- KG update receipt.

```python
class Receipt(BaseModel):
    receipt_id: str
    session_id: str
    run_id: str | None
    kind: str
    action: str
    reason: str
    evidence_refs: list[str]
    cost: dict[str, Any]
    created_at: str
```

Every expensive or mutating operation must create a receipt.

---

# 21. Checkpoints and Rollback

Before file mutation, the Runtime must create a checkpoint.

```python
class Checkpoint(BaseModel):
    checkpoint_id: str
    session_id: str
    run_id: str
    files: list[str]
    checksums: dict[str, str]
    created_at: str
```

Rollback must be possible for:

- failed mutation;
- failed inspection;
- policy violation;
- user rejection.

---

# 22. Policy Enforcement

Every operation that can affect the workspace must pass through the Policy Engine.

Policy-governed operations:

- file read;
- file write;
- command execution;
- network access;
- provider call;
- memory write;
- KG write;
- plugin execution.

The Runtime must never rely on prompt instructions for policy enforcement.

---

# 23. Capability Checks

Before executing a node, the Runtime checks required capabilities.

Examples:

- git;
- terminal;
- pytest;
- phpunit;
- phpstan;
- phpcs;
- npm;
- docker;
- host sampling;
- KG index.

If a capability is missing, the Runtime must:

1. degrade gracefully if possible;
2. record the missing capability;
3. suggest configuration;
4. block only when required.

---

# 24. Provider Gateway

The Runtime must not call model providers directly from workflow nodes.

All model execution goes through Provider Gateway.

Provider Gateway responsibilities:

- provider selection;
- model selection;
- structured output support;
- token accounting;
- retries;
- safety limits;
- redaction;
- streaming.

---

# 25. Runtime Modes

Supported modes:

```text
run_to_completion
interactive
step
dry_run
simulate
resume
```

## run_to_completion

Default for simple user tasks.

## interactive

Used when approvals or clarifications are expected.

## step

Used by advanced agents and Studio.

## dry_run

No mutations.

## simulate

Predict cost/risk/workflow without execution.

## resume

Continue a paused session.

---

# 26. Runtime Profiles

Profiles configure default behaviour.

Built-in profiles:

- balanced
- low-cost
- enterprise
- research
- performance

Profiles must not change architecture.

They only change defaults.

---

# 27. Error Handling

Runtime errors must be typed.

```python
class RuntimeErrorCode(StrEnum):
    WORKFLOW_NOT_FOUND = "workflow_not_found"
    INVALID_TRANSITION = "invalid_transition"
    POLICY_DENIED = "policy_denied"
    CAPABILITY_MISSING = "capability_missing"
    OUTPUT_CONTRACT_FAILED = "output_contract_failed"
    MUTATION_FAILED = "mutation_failed"
    INSPECTION_FAILED = "inspection_failed"
    PROVIDER_FAILED = "provider_failed"
    RESUME_FAILED = "resume_failed"
```

Errors must include:

- message;
- recoverability;
- next recommended action;
- evidence refs;
- user-facing summary.

---

# 28. Resume Semantics

Resume must be artifact-aware.

It is not enough to skip completed nodes.

Resume must rehydrate:

- session state;
- workflow state;
- artifacts;
- receipts;
- context contracts;
- memory references;
- policy decisions;
- previous gates.

If required artifacts are missing, resume must fail safely with clear explanation.

---

# 29. Escalation

Escalation is a valid runtime outcome.

It is not a failure of governance.

Escalation occurs when:

- attempts exhausted;
- policy requires human approval;
- confidence too low;
- missing context;
- high-risk surface;
- owner input required.

Escalation must produce:

- report;
- handoff;
- blocking reason;
- owner candidates;
- next action.

---

# 30. Consolidation

Consolidation happens after completion or escalation.

It performs:

- artifact finalization;
- memory candidate extraction;
- KG delta update;
- summary generation;
- L1 context purge;
- event finalization;
- cost report;
- confidence report.

Consolidation must not save noisy execution details as durable memory.

---

# 31. Runtime Intelligence Integration

The Runtime should call Runtime Intelligence for:

- workflow selection;
- cost estimation;
- confidence scoring;
- simulation;
- profiling;
- benchmark reporting;
- evolution proposal.

Runtime Intelligence may recommend.

It may not silently override policies.

---

# 32. Security Requirements

The Runtime must enforce:

- path containment;
- forbidden path policy;
- secret redaction;
- network restrictions;
- command allow/deny rules;
- provider redaction;
- plugin permissions.

No workflow, persona or skill may bypass security checks.

---

# 33. Performance Requirements

Runtime overhead should be measurable.

The Runtime should track:

- total duration;
- token usage;
- local command time;
- retrieval time;
- provider latency;
- event writing time;
- inspection time;
- diagnosis attempts.

Performance improvements must be benchmarked.

---

# 34. First-Run Requirement

A clean installation must support:

```bash
opencontext init --profile balanced
opencontext index
opencontext run "Fix failing test" --workflow auto
```

Expected behaviour:

- capabilities detected;
- workflow selected;
- context retrieved surgically;
- mutation applied safely;
- local inspection executed;
- summary returned;
- artifacts persisted.

---

# 35. Migration Plan from Current Branch

Phase 1:

- wrap current `HarnessRunner.run()` in RuntimeSession;
- emit RuntimeEvents;
- improve `opencontext_run` response.

Phase 2:

- add WorkflowRegistry;
- register current SDD;
- map legacy workflow aliases.

Phase 3:

- introduce ArtifactStore and ReceiptStore;
- make ApplyPhase produce receipts.

Phase 4:

- introduce OC Flow;
- use same Runtime.

Phase 5:

- move personas and skills to registries;
- add harness registry.

Phase 6:

- add KG/memory/compression v2;
- add Runtime Intelligence.

---

# 36. Runtime Invariants

1. Every run belongs to a session.
2. Every workflow transition is validated.
3. Every major action emits an event.
4. Every mutation has a checkpoint.
5. Every mutation has a receipt.
6. Every workflow selection has a receipt.
7. Every expensive retrieval is budgeted.
8. Every policy decision is logged.
9. Every durable output is an artifact.
10. Resume rehydrates artifacts.
11. Interfaces never bypass Runtime API.
12. Runtime remains workflow-neutral.

---

# 37. Definition of Done

The Runtime Architecture is implemented when:

- MCP and CLI use Runtime API;
- sessions are first-class;
- SDD executes through WorkflowRunner;
- OC Flow executes through WorkflowRunner;
- events are persisted;
- artifacts are persisted;
- receipts are persisted;
- policies are enforced;
- resume works with artifacts;
- opencontext_run returns useful summaries;
- Runtime Intelligence can estimate and report cost/confidence;
- Studio can render live state.

---

# 38. Final Statement

The Runtime is the heart of OpenContext.

It must be boring, deterministic, observable and strict.

The agent may be creative.

The Runtime must be reliable.
