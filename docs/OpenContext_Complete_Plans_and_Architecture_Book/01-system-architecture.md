# OpenContext System Architecture
## Version 1.0 (Draft)
### Document ID
OC-ARCH-001

### Status
Draft

### Depends on
- `00-engineering-principles.md`

---

# 1. Purpose

This document defines the target system architecture for OpenContext.

It describes how the major subsystems fit together, which responsibilities each subsystem owns, which boundaries must remain stable, and how the current `feat/agentic-engineering-runtime` branch should evolve into the complete OpenContext Engineering Operating System.

This document is not an implementation guide for a single feature.

It is the architectural reference for the whole product.

---

# 2. Architectural Goal

OpenContext must become a modular, deterministic and observable engineering runtime where multiple workflows can coexist.

The first two first-class workflows are:

- **SDD Workflow** — formal, spec-driven, high-traceability engineering.
- **OC Flow** — operational, fast, local-first agentic engineering.

Both workflows share the same infrastructure:

- Runtime
- Workflow Registry
- Session Store
- Event Bus
- Knowledge Graph
- Memory
- Context Engineering
- Compression
- Harness Registry
- Persona Registry
- Skill Registry
- Policy Engine
- Capability Registry
- Runtime Intelligence
- Studio
- Plugin SDK
- MCP / CLI / IDE adapters

No workflow should own infrastructure that belongs to the platform.

---

# 3. Core Architectural Principle

OpenContext is not built around a single agent.

OpenContext is built around a governed runtime.

The correct dependency direction is:

```text
User Interfaces
  -> Runtime API
    -> Workflow Engine
      -> Harnesses / Policies / Capabilities
        -> KG / Memory / Context / Tools
```

The incorrect dependency direction is:

```text
Agent prompt
  -> decides everything
```

The runtime owns orchestration.

The model contributes reasoning.

---

# 4. Top-Level Architecture

```text
OpenContext
│
├── Interfaces
│   ├── MCP Server
│   ├── CLI
│   ├── TUI
│   ├── Studio
│   └── IDE Adapters
│
├── Runtime Core
│   ├── Session Runtime
│   ├── Workflow Engine
│   ├── State Machine
│   ├── Event Bus
│   ├── Artifact Store
│   └── Receipt Store
│
├── Workflow Layer
│   ├── Workflow Registry
│   ├── SDD Workflow
│   ├── OC Flow
│   ├── Workflow Selector
│   └── Workflow Definitions
│
├── Governance Layer
│   ├── Harness Registry
│   ├── Policy Engine
│   ├── Capability Registry
│   ├── Approval Gates
│   └── Security Gates
│
├── Intelligence Layer
│   ├── Knowledge Graph
│   ├── Memory
│   ├── Context Retrieval
│   ├── Compression
│   ├── Cost Engine
│   ├── Confidence Engine
│   └── Runtime Simulator
│
├── Agent Layer
│   ├── Persona Registry
│   ├── Skill Registry
│   ├── Delegation
│   └── Provider Gateway
│
├── Evaluation Layer
│   ├── Benchmarks
│   ├── Runtime Health
│   ├── Harness Evaluation
│   └── Evolution Engine
│
└── Extension Layer
    ├── Plugin SDK
    ├── Provider Adapters
    ├── KG Providers
    ├── Memory Providers
    ├── Evaluators
    └── Studio Panels
```

---

# 5. Layer Responsibilities

## 5.1 Interfaces

Interfaces expose OpenContext to users and external agents.

They must not own business logic.

Examples:

- MCP tools
- CLI commands
- TUI views
- Studio UI
- IDE integrations

Interface responsibilities:

- parse input
- call Runtime API
- render output
- stream events
- show artifacts
- request approvals

Interfaces must never bypass:

- policies
- harnesses
- session lifecycle
- artifact receipts
- event logging

---

## 5.2 Runtime Core

The Runtime Core owns execution.

Responsibilities:

- create sessions
- execute workflows
- validate state transitions
- emit events
- persist artifacts
- coordinate harnesses
- enforce policies
- manage checkpoints
- support resume
- produce summaries

The runtime must not contain SDD-specific or OC Flow-specific logic.

It executes `WorkflowDefinition`.

---

## 5.3 Workflow Layer

The Workflow Layer defines engineering processes.

A workflow is a graph of nodes, edges, roles, required capabilities, required skills, required harnesses and output contracts.

The first built-in workflows are:

```text
sdd
oc-flow
quick
review
```

The runtime must be able to add more workflows without changing core orchestration code.

---

## 5.4 Governance Layer

The Governance Layer decides what is allowed.

It includes:

- policy evaluation
- capability checks
- approval gates
- security gates
- harness execution
- rollback requirements
- path restrictions
- command restrictions

The Governance Layer is mandatory for all workflows.

No mutation should bypass it.

---

## 5.5 Intelligence Layer

The Intelligence Layer provides knowledge and decision support.

It includes:

- code graph
- temporal knowledge graph
- memory
- context envelopes
- semantic compression
- cost estimation
- confidence scoring
- runtime simulation

The Intelligence Layer reduces unnecessary model usage.

---

## 5.6 Agent Layer

The Agent Layer provides model-mediated reasoning.

It includes:

- personas
- skills
- delegation
- provider gateway
- structured output protocols

The Agent Layer must be subordinate to the Runtime Core.

Agents do not own execution.

They produce proposed outputs that the runtime validates.

---

## 5.7 Evaluation Layer

The Evaluation Layer measures quality.

It includes:

- first-run benchmarks
- workflow benchmarks
- skill benchmarks
- harness benchmarks
- KG retrieval benchmarks
- memory benchmarks
- runtime health checks
- evolution proposals

No runtime improvement should be adopted without evidence.

---

## 5.8 Extension Layer

The Extension Layer enables third-party integrations.

Plugins may contribute:

- workflows
- skills
- personas
- harnesses
- policies
- evaluators
- KG providers
- memory providers
- Studio panels

Plugins must integrate through stable contracts.

---

# 6. Dependency Rules

Dependencies must flow inward.

Allowed:

```text
Interface -> Runtime API
Runtime -> Workflow Definition
Runtime -> Harness Registry
Runtime -> Policy Engine
Runtime -> Event Bus
Harness -> KG / Memory / Tools
Workflow -> Persona / Skill IDs
Persona -> Skill IDs
Skill -> Gates / Output Contracts
```

Forbidden:

```text
MCP tool -> direct file mutation
Persona -> direct policy bypass
Skill -> workflow orchestration
Workflow -> hardcoded provider
Harness -> UI rendering
Memory -> runtime transition
KG -> model call
Plugin -> private runtime internals
```

---

# 7. Runtime API Boundary

All external interfaces must call the Runtime API.

Minimum Runtime API:

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
```

No interface should instantiate workflow phases directly.

---

# 8. Session as the Primary Unit

A session is the top-level execution container.

A session may contain one or more runs.

A run executes one workflow.

Example:

```text
Session: improve-agentic-runtime
  Run 1: sdd
  Run 2: oc-flow
  Run 3: review
```

Session responsibilities:

- store task
- store workflow choice
- store context ID
- store config snapshot
- store events
- store artifacts
- store receipts
- support resume
- support archive

---

# 9. Workflow as a Definition

A workflow must be declarative.

```yaml
schema_version: opencontext.workflow.v1
id: oc-flow
label: OpenContext Agentic Flow
start_node: init
terminal_nodes:
  - completed
nodes:
  init:
    role: orchestrator
    harnesses:
      - context.bootstrap
edges:
  - from_node: init
    to_node: gather_context
```

The runtime interprets the graph.

The workflow does not execute itself.

---

# 10. SDD Architecture

SDD remains a first-class workflow.

It is not replaced by OC Flow.

SDD phases:

```text
explore
propose
spec
design
tasks
apply
verify
review
archive
```

SDD is optimized for:

- high-risk features
- API changes
- architecture changes
- multi-module work
- formal planning
- traceability
- long-lived artifacts

SDD must use the same runtime infrastructure as OC Flow.

---

# 11. OC Flow Architecture

OC Flow is a first-class operational workflow.

OC Flow nodes:

```text
init
gather_context
plan
mutate
local_inspection
diagnose
escalation
consolidation
completed
```

OC Flow is optimized for:

- bugfixes
- small features
- refactors
- lint/type/test failures
- maintenance
- low-token execution
- fast feedback

OC Flow must not duplicate SDD infrastructure.

---

# 12. Workflow Selection

Workflow selection is a runtime decision.

It must consider:

- task type
- risk
- expected blast radius
- available tests
- KG confidence
- memory signals
- cost estimate
- user profile
- policy constraints

The selector may return:

```json
{
  "selected": "oc-flow",
  "confidence": 0.86,
  "reason": "Localized bugfix with low blast radius",
  "alternatives": ["sdd"]
}
```

The selection decision must be recorded.

---

# 13. Harness Architecture

Harnesses are reusable governance components.

They are not tied to a single workflow.

Examples:

- context harness
- planning harness
- mutation harness
- inspection harness
- diagnosis harness
- review harness
- security harness
- memory harness
- KG harness
- consolidation harness

Each harness must define:

- inputs
- outputs
- gates
- mode
- metrics
- failure behaviour

---

# 14. Persona Architecture

Personas define engineering responsibilities.

A persona is not a personality prompt.

A persona must define:

- responsibility
- allowed tools
- required skills
- output contracts
- compatible workflows
- compatible nodes
- forbidden behaviours

Personas are reusable across workflows.

Example:

```text
oc-builder
  used by SDD apply
  used by OC Flow mutate
```

---

# 15. Skill Architecture

Skills define reusable engineering procedures.

A skill must define:

- trigger
- tier
- applicable workflows
- applicable personas
- compact rules
- required outputs
- gates
- examples
- failure modes
- token budget

Skills must be independently testable.

Skills must not own workflow routing.

---

# 16. Knowledge Graph Architecture

The Knowledge Graph stores structural and temporal engineering knowledge.

It should include:

- files
- symbols
- imports
- calls
- tests
- owners
- decisions
- failures
- artifacts
- sessions
- skills
- harnesses

The graph must support:

- surgical context retrieval
- impact analysis
- owner resolution
- test discovery
- memory grounding
- consolidation after runs

---

# 17. Memory Architecture

Memory stores durable knowledge.

Memory is divided into:

- episodic memory
- semantic memory
- procedural memory
- project memory
- failure pattern memory
- harness experience memory

Memory must be evidence-backed.

Memory must support expiry, supersession and conflict detection.

---

# 18. Compression Architecture

Compression reduces token waste while preserving engineering truth.

Compression targets:

- context
- logs
- failures
- memory
- conversations
- artifacts
- KG neighborhoods

Compression must preserve:

- constraints
- decisions
- evidence
- failed strategies
- current error
- next action

---

# 19. Runtime Intelligence Architecture

Runtime Intelligence provides:

- cost estimation
- confidence scoring
- runtime simulation
- profiling
- benchmarking
- runtime health
- evolution proposals

Runtime Intelligence must not silently change runtime behaviour.

It proposes.

The runtime or user approves.

---

# 20. Event Architecture

Every significant action emits an event.

Required event families:

- session events
- workflow events
- node events
- persona events
- skill events
- harness events
- policy events
- KG events
- memory events
- mutation events
- inspection events
- diagnosis events
- escalation events
- consolidation events

Events must be machine-readable.

---

# 21. Artifact Architecture

Artifacts are durable outputs.

Examples:

- context envelopes
- specs
- designs
- task contracts
- patches
- receipts
- inspection reports
- diagnosis reports
- escalation reports
- summaries
- memory deltas
- graph deltas

Artifacts must be referenced by ID and path.

No major output should exist only in chat.

---

# 22. Receipt Architecture

Receipts are proof of action.

Every expensive or mutating action must generate a receipt.

Receipt examples:

- context retrieval receipt
- workflow selection receipt
- apply receipt
- inspection receipt
- policy receipt
- memory write receipt
- graph update receipt
- escalation receipt

Receipts support auditability.

---

# 23. Policy Architecture

Policies are runtime-enforced rules.

They are not prompt instructions.

Policies govern:

- file reads
- file writes
- command execution
- network access
- secrets
- providers
- memory writes
- auto-apply
- approvals

Every policy decision must be logged.

---

# 24. Capability Architecture

Capabilities describe what the environment can do.

Examples:

- git
- terminal
- pytest
- phpunit
- phpstan
- phpcs
- npm
- eslint
- docker
- KG index
- host sampling
- OpenTelemetry

Workflows and harnesses must adapt to capabilities.

---

# 25. Provider Architecture

Providers supply model execution or external services.

The runtime must not depend on a specific provider.

Providers must expose:

- capabilities
- cost model
- context limits
- streaming support
- structured output support
- safety constraints

---

# 26. Plugin Architecture

Plugins extend OpenContext through manifests.

Plugins may provide:

- workflows
- skills
- personas
- harnesses
- providers
- policies
- evaluators
- KG providers
- memory providers
- Studio panels

Plugins must be permissioned and versioned.

---

# 27. Studio Architecture

OpenContext Studio is the visual control plane.

Studio must show:

- live workflow state
- events
- traces
- context used
- memory used
- KG subgraph
- skills
- personas
- harnesses
- patches
- receipts
- costs
- confidence
- benchmarks
- runtime health

Studio reads runtime artifacts.

Studio must not become required for headless operation.

---

# 28. Configuration Architecture

Configuration must be centralized.

Primary config:

```text
opencontext.yaml
```

Configuration areas:

- workflow
- runtime
- context
- memory
- KG
- compression
- personas
- skills
- harnesses
- policies
- capabilities
- providers
- observability
- runtime intelligence
- plugins

Profiles simplify configuration.

Examples:

- balanced
- low-cost
- enterprise
- research
- performance

---

# 29. Public vs Internal APIs

Public APIs are stable contracts.

Examples:

- WorkflowDefinition
- SkillDefinition
- PersonaDefinition
- HarnessDefinition
- RuntimeEvent
- Receipt
- ArtifactRef
- MemoryRecord
- KG node/edge schema
- PolicyDecision
- PluginManifest

Internal APIs may change.

Any plugin-facing API is public.

---

# 30. Migration from Current Branch

The current `feat/agentic-engineering-runtime` branch already contains important foundations:

- MCP tools
- HarnessRunner
- SDD phases
- PhaseResultEnvelope
- ApplyEdit
- delegation
- personas
- skill resolver
- harness config
- memory provenance
- run events
- gates

Migration should not rewrite everything.

Migration order:

1. Stabilize current SDD behaviour.
2. Introduce RuntimeSession.
3. Introduce WorkflowRegistry.
4. Register SDD declaratively.
5. Add improved event/artifact/receipt model.
6. Harden existing SDD phases.
7. Add OC Flow as new workflow.
8. Promote personas to registry.
9. Promote skills to contracts.
10. Add harness registry.
11. Add KG/memory/compression v2.
12. Add Runtime Intelligence.
13. Add Studio and Plugin SDK.

---

# 31. Architectural Invariants

The following invariants must never be broken:

1. Interfaces do not bypass Runtime API.
2. Workflows do not mutate files directly.
3. Personas do not own orchestration.
4. Skills do not own workflow routing.
5. Harnesses are reusable across workflows.
6. Policies are enforced by runtime, not prompts.
7. Mutations require receipts.
8. Expensive decisions require evidence.
9. Context retrieval is budgeted.
10. Memory writes are evidence-backed.
11. Events are emitted for significant actions.
12. Artifacts are persisted outside chat.
13. Plugins integrate through stable contracts.
14. SDD and OC Flow remain independent workflows.
15. Runtime remains workflow-neutral.

---

# 32. Definition of Done

This architecture is implemented when:

- SDD works through the shared runtime.
- OC Flow works through the shared runtime.
- WorkflowRegistry exists.
- SessionRuntime exists.
- HarnessRegistry exists.
- PersonaRegistry exists.
- SkillRegistry v2 exists.
- KG and memory integrate with context retrieval.
- Compression is used before large prompts.
- Policies enforce runtime decisions.
- Events and receipts are persisted.
- Runtime Intelligence can estimate cost/confidence.
- Studio can visualize executions.
- Plugins can extend the system safely.
- First install can complete a real task with good defaults.

---

# 33. Final Statement

OpenContext must be architected as a platform, not as a collection of agent prompts.

The system succeeds when every workflow, skill, persona, harness, memory record and graph edge participates in one coherent engineering loop:

```text
Understand
↓
Retrieve
↓
Plan
↓
Act
↓
Verify
↓
Learn
↓
Explain
```

That loop is the product.
