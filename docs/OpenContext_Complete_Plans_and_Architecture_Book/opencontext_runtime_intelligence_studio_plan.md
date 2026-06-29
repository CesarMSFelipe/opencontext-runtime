# OpenContext Runtime Intelligence & Studio v1

**Documento complementario a:**
1. `OpenContext Agentic Runtime v4 — SDD + OC Flow`
2. `OpenContext Skill Ecosystem v2`
3. `OpenContext Cognitive Runtime v1 — KG, Memory, Compression & Harnesses`

**Ámbito:** runtime intelligence, self-evolving runtime, cost engine, confidence engine, simulator, observability, benchmarks, policies, plugin SDK, OpenContext Studio y organization intelligence.

---

## 0. Resumen ejecutivo

Los planes anteriores convierten OpenContext en:

```text
Runtime agentic
+ SDD y OC Flow
+ Skills/personas/harnesses
+ KG/memoria/compresión
```

Pero para estar realmente a la vanguardia durante varios años falta una capa más:

```text
Runtime Intelligence
```

Esta capa observa cómo funciona OpenContext, mide resultados, estima costes, calcula confianza, simula decisiones antes de ejecutarlas, recomienda mejoras, valida esas mejoras con benchmarks y presenta todo en una consola de ingeniería.

El objetivo:

> OpenContext no solo debe ejecutar tareas. Debe entender su propio rendimiento, explicar sus decisiones y mejorar su configuración/harnesses/skills con evidencia.

---

## 1. Estado del arte revisado

### 1.1 LangSmith

LangSmith es referencia clara en observabilidad de aplicaciones LLM: trazas individuales, métricas en producción, debugging, dashboards, feedback, evaluaciones online y automatizaciones. Su documentación posiciona la observabilidad como visibilidad completa desde trazas individuales hasta métricas de producción.

**Qué adoptar en OpenContext:**

- trace-first UX;
- dashboards;
- recurring issue detection;
- feedback queues;
- online evaluations;
- prompt/version experimentation;
- production monitoring.

**Qué no copiar tal cual:**

- LangSmith es plataforma general de LLM apps; OpenContext debe ser específico de ingeniería de software, con patches, tests, KG, harnesses, symbols, owners y workflows.

---

### 1.2 Langfuse

Langfuse aporta una arquitectura muy completa: observabilidad, prompt management, evaluation, datasets, experiments, sesiones, costes, latencia y agent graphs. También es open source/self-hostable y se basa en OpenTelemetry para reducir vendor lock-in.

**Qué adoptar en OpenContext:**

- prompts/versiones vinculados a traces;
- datasets/experiments;
- agent graph visualization;
- cost/latency dashboards;
- self-hostable;
- sessions as first-class;
- traces con retrieval/tool calls;
- evaluación en desarrollo y producción.

---

### 1.3 Arize Phoenix / OpenInference

Phoenix destaca por tracing, evaluación, datasets, experiments, prompt engineering y replay de spans. Su enfoque de “de inspeccionar runs individuales a mejorar calidad con evidencia” encaja perfectamente con OpenContext.

**Qué adoptar en OpenContext:**

- span replay;
- experiment comparison;
- prompt variants;
- dataset-driven evals;
- evaluator results attached to spans;
- OpenTelemetry/OpenInference compatibility.

---

### 1.4 OpenTelemetry GenAI

OpenTelemetry ya tiene convenciones para GenAI y ha movido sus convenciones GenAI a un repositorio dedicado. La dirección del mercado es clara: los agentes necesitan trazas interoperables, no solo logs privados.

**Qué adoptar en OpenContext:**

- export OTLP;
- semantic attributes para model calls, tool calls, MCP calls, retrieval, memory, prompts;
- vendor-neutral observability;
- compatible con Langfuse/Phoenix/LangSmith cuando sea posible.

---

### 1.5 DSPy / TextGrad / APE / prompt optimization

La optimización automática de prompts puede mejorar rendimiento, pero investigaciones recientes muestran que no siempre transfiere; puede fallar por interacción con la tarea. Hay estudios que recomiendan test de “headroom” antes de optimizar y muestran que la optimización funciona mejor cuando hay estructura explotable.

**Qué adoptar en OpenContext:**

- no optimizar prompts a ciegas;
- optimizar solo con datasets/evals;
- hacer pre-test de headroom;
- proponer cambios, no aplicarlos sin benchmark;
- optimizar skills/harness instructions por tarea/workflow.

---

### 1.6 Voyager

Voyager muestra un patrón muy potente: skill library creciente, feedback del entorno, self-verification y reutilización de habilidades aprendidas.

**Qué adoptar en OpenContext:**

- biblioteca de skills/procedimientos aprendidos;
- skills composables;
- learning from execution feedback;
- promote only verified skills;
- avoid catastrophic forgetting via versioned skill library.

---

### 1.7 AlphaEvolve / CodeEvolve / FunSearch

Estos sistemas demuestran el valor de un loop evolutivo:

```text
candidate generation
-> automated evaluation
-> selection
-> mutation/crossover
-> next candidate
```

Clave: necesitan evaluadores programáticos. Sin evaluadores, la evolución se vuelve peligrosa o inútil.

**Qué adoptar en OpenContext:**

- evolution engine para prompts/skills/harness configs;
- candidate variants;
- benchmark gates;
- multi-objective optimization: success, tokens, time, changed lines, security;
- no self-modification sin evaluación reproducible.

---

### 1.8 SWE-agent / OpenHands / SWE-bench ecosystem

SWE-agent mostró que el Agent-Computer Interface importa mucho. Benchmarks como SWE-bench, FeatureBench y SecureAgentBench muestran que bugfix, feature development y secure coding son dimensiones distintas.

**Qué adoptar en OpenContext:**

- evaluation by executable tests;
- coding-agent interface design as product;
- separate benchmarks:
  - bugfix;
  - features;
  - security;
  - refactor;
  - documentation;
  - framework-specific;
- measure cost and correctness together.

---

## 2. Problema que resuelve esta capa

Sin Runtime Intelligence, OpenContext puede ejecutar bien, pero no sabrá responder:

```text
¿Por qué eligió OC Flow?
¿Cuánto habría costado SDD?
¿Qué parte del runtime consume más tokens?
¿Qué skill causa más fallos?
¿Qué harness bloquea demasiado?
¿Qué memoria está obsoleta?
¿Qué prompt empeoró después del último cambio?
¿Qué configuración recomienda para este repo?
¿Qué benchmark demuestra que esta mejora es real?
```

Runtime Intelligence debe convertir esas preguntas en datos.

---

## 3. Arquitectura final

```text
OpenContext Runtime Intelligence
│
├── Observability Core
│   ├── traces
│   ├── spans
│   ├── events
│   ├── provenance
│   ├── decisions
│   └── metrics
│
├── Cost Engine
│   ├── pre-run estimator
│   ├── live cost tracker
│   ├── post-run accounting
│   └── what-if comparison
│
├── Confidence Engine
│   ├── context confidence
│   ├── plan confidence
│   ├── mutation confidence
│   ├── verification confidence
│   └── overall confidence
│
├── Runtime Simulator
│   ├── dry-run cognitive simulation
│   ├── workflow recommendation
│   ├── risk prediction
│   └── expected artifact graph
│
├── Evolution Engine
│   ├── candidate generation
│   ├── benchmark execution
│   ├── promotion policy
│   ├── rollback
│   └── evidence report
│
├── Benchmark System
│   ├── first-run benchmarks
│   ├── workflow benchmarks
│   ├── skill benchmarks
│   ├── harness benchmarks
│   ├── security benchmarks
│   └── framework benchmarks
│
├── Organization Intelligence
│   ├── org graph
│   ├── owners
│   ├── teams
│   ├── services
│   ├── incidents
│   └── knowledge domains
│
├── Policy Runtime
│   ├── policy DSL
│   ├── enforcement
│   ├── audit
│   └── approvals
│
├── Plugin Platform
│   ├── SDK
│   ├── manifests
│   ├── extension points
│   ├── sandbox
│   └── marketplace/private registry
│
└── OpenContext Studio
    ├── live workflow view
    ├── KG view
    ├── trace explorer
    ├── cost dashboard
    ├── confidence dashboard
    ├── benchmark dashboard
    └── config/profile editor
```

---

## 4. Observability Core

### 4.1 Objetivo

Toda acción importante debe ser trazable:

- workflow selected;
- persona selected;
- skills loaded;
- context retrieved;
- memory used;
- LLM call;
- tool call;
- mutation;
- local inspection;
- diagnosis;
- escalation;
- consolidation.

### 4.2 Trace model

```python
class OcTrace(BaseModel):
    trace_id: str
    session_id: str
    run_id: str
    workflow: str
    task: str
    root: str
    started_at: datetime
    ended_at: datetime | None
    status: str
    spans: list[OcSpan]
    metrics: TraceMetrics
```

### 4.3 Span model

```python
class OcSpan(BaseModel):
    span_id: str
    parent_span_id: str | None
    name: str
    kind: Literal[
        "workflow",
        "node",
        "persona",
        "skill",
        "harness",
        "llm",
        "tool",
        "mcp",
        "retrieval",
        "memory",
        "mutation",
        "inspection",
        "diagnosis",
        "policy",
        "benchmark"
    ]
    start_time: datetime
    end_time: datetime | None
    status: str
    attributes: dict[str, Any]
    inputs_ref: str | None
    outputs_ref: str | None
    evidence_refs: list[str]
```

### 4.4 OpenTelemetry export

OpenContext should support:

```yaml
observability:
  exporters:
    jsonl: true
    otlp: false
    langfuse: false
    phoenix: false
    langsmith: false
```

### 4.5 Evidence tracing

Cada afirmación importante en resumen final debe enlazar con:

- file lines;
- tool output;
- test output;
- memory record;
- KG node;
- run artifact.

---

## 5. Cost Engine

### 5.1 Objetivo

Antes de ejecutar, estimar:

```text
workflow
tokens
tool calls
time
risk
success probability
```

### 5.2 Pre-run estimate

```python
class CostEstimate(BaseModel):
    workflow: str
    lane: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_tool_calls: int
    estimated_local_commands: int
    estimated_time_s: int
    estimated_cost_usd: float | None
    confidence: float
    assumptions: list[str]
```

### 5.3 What-if comparison

For `workflow=auto`:

```text
OC Flow
  tokens: ~5k
  time: ~45s
  success: 0.82
  risk: low

SDD
  tokens: ~18k
  time: ~3m
  success: 0.91
  risk: lower
```

### 5.4 Post-run accounting

```python
class CostReport(BaseModel):
    estimated: CostEstimate
    actual_input_tokens: int
    actual_output_tokens: int
    actual_tool_calls: int
    actual_duration_s: int
    estimate_error_pct: float
    cost_by_component: dict[str, float]
```

### 5.5 Token saving attribution

Report:

```text
Saved by KG signatures: 8,400 tokens
Saved by semantic compression: 3,100 tokens
Saved by local inspection: 1 LLM call avoided
```

---

## 6. Confidence Engine

### 6.1 Objetivo

No basta con “pasó/falló”. El runtime debe saber con qué confianza está actuando.

### 6.2 Dimensions

```text
intent_confidence
context_confidence
plan_confidence
mutation_confidence
inspection_confidence
security_confidence
memory_confidence
overall_confidence
```

### 6.3 ConfidenceReport

```python
class ConfidenceReport(BaseModel):
    session_id: str
    run_id: str
    workflow: str
    dimensions: dict[str, ConfidenceDimension]
    overall: float
    threshold: float
    action: Literal["continue", "ask_user", "switch_workflow", "deep_mode", "escalate"]
```

### 6.4 Signals

#### Context confidence

- exact symbol match;
- tests found;
- owners found;
- KG freshness;
- no unresolved omissions.

#### Plan confidence

- acceptance criteria present;
- constraints clear;
- risk mapped;
- no contradictions.

#### Mutation confidence

- small diff;
- tests pass;
- no public API change;
- type/lint pass;
- no forbidden paths.

#### Security confidence

- no secrets;
- no auth/billing/trust boundary;
- security harness pass.

### 6.5 Actions

If confidence low:

```text
ask clarifying question
retrieve deeper context
switch OC Flow -> SDD
require approval
escalate to owner
```

---

## 7. Runtime Simulator

### 7.1 Objetivo

Antes de ejecutar, simular el plan:

```text
What will likely be touched?
Which workflow?
Which harnesses?
Which risks?
Which tests?
Expected cost?
Expected confidence?
```

### 7.2 SimulationReport

```python
class SimulationReport(BaseModel):
    task: str
    recommended_workflow: str
    recommended_lane: str
    expected_files: list[str]
    expected_symbols: list[str]
    expected_tests: list[str]
    expected_harnesses: list[str]
    risk_flags: list[str]
    cost_estimates: list[CostEstimate]
    confidence_estimate: float
    recommendation: str
```

### 7.3 Modes

```bash
opencontext simulate "Add session resume"
opencontext run "Add session resume" --dry-run
```

### 7.4 UX

Output:

```text
I recommend SDD because this affects runtime session persistence and resume behavior.

Expected:
- 4-7 files
- session_store, harness runner, tests
- moderate risk
- ~16k tokens

Alternative:
- OC Flow could be cheaper but may miss design implications.
```

---

## 8. Evolution Engine

### 8.1 Objetivo

El runtime debe mejorar, pero nunca de forma opaca.

```text
observe
  -> detect pattern
  -> propose improvement
  -> generate candidate
  -> benchmark
  -> compare
  -> approve
  -> promote
```

### 8.2 What can evolve

- skill prompts;
- skill routing;
- persona contracts;
- harness configs;
- workflow selector thresholds;
- context retrieval policies;
- compression policies;
- cost estimator weights;
- confidence thresholds.

### 8.3 What cannot evolve automatically

- user code;
- security policies;
- provider credentials;
- destructive operations;
- core runtime code without approval.

### 8.4 EvolutionCandidate

```python
class EvolutionCandidate(BaseModel):
    candidate_id: str
    target_type: Literal["skill", "persona", "harness", "workflow", "policy", "retrieval"]
    target_id: str
    change_summary: str
    patch: str
    rationale: str
    expected_benefit: str
    risks: list[str]
    generated_from_runs: list[str]
    required_benchmarks: list[str]
```

### 8.5 Evaluation gate

A candidate cannot be promoted unless:

- benchmarks pass;
- token cost not worse beyond threshold;
- security not worse;
- first-run benchmark not worse;
- human approval if public/builtin.

### 8.6 Optimizers

Supported approaches:

```text
manual proposal
A/B prompt variant
DSPy-like optimization
TextGrad-like critique loop
evolutionary variants
bandit selection
```

Default:

```text
manual proposal + benchmark
```

No blind self-optimization.

---

## 9. Benchmark System

### 9.1 Benchmark types

```text
first_run
bugfix
feature
secure_coding
refactor
docs
framework_specific
memory
kg_retrieval
workflow_selection
harness
skill
persona
cost_estimation
confidence_calibration
```

### 9.2 Benchmark task schema

```python
class BenchmarkTask(BaseModel):
    id: str
    name: str
    repo_fixture: str
    task: str
    expected_workflow: str | None
    setup_commands: list[str]
    eval_commands: list[str]
    success_criteria: list[str]
    security_checks: list[str]
    max_tokens: int | None
    max_changed_lines: int | None
```

### 9.3 Benchmark result

```python
class BenchmarkResult(BaseModel):
    task_id: str
    candidate_id: str | None
    success: bool
    tokens: int
    duration_s: int
    tool_calls: int
    changed_files: int
    changed_lines: int
    tests_passed: bool
    security_passed: bool
    confidence_calibration_error: float | None
```

### 9.4 Required suites

#### Core

- first install;
- first OC Flow bugfix;
- first SDD feature;
- resume session;
- escalation.

#### Coding

- Python;
- TypeScript;
- PHP;
- Drupal/Symfony;
- monorepo;
- docs-only.

#### Security

- auth change;
- secret exposure;
- command injection;
- dependency upgrade.

#### Context

- KG stale;
- memory conflict;
- broad context avoided;
- wrong owner fallback.

---

## 10. Runtime Profiler

### 10.1 Objective

Show where time/tokens go.

```text
Context retrieval: 38%
LLM planning: 14%
Mutation: 8%
Inspection: 5%
Diagnosis: 31%
Consolidation: 4%
```

### 10.2 ProfilerReport

```python
class ProfilerReport(BaseModel):
    session_id: str
    cost_by_component: dict[str, CostBlock]
    bottlenecks: list[str]
    recommendations: list[ProfilerRecommendation]
```

### 10.3 Recommendations

Examples:

```text
Create persistent context bundle for package X.
Lower diagnosis attempts from 3 to 2.
Enable targeted test command for PHPStan.
Split context file over 800 LOC.
Promote repeated command to procedural memory.
```

---

## 11. Runtime Health

### 11.1 Health dimensions

```text
KG freshness
memory quality
skill catalog health
harness pass rate
workflow selector accuracy
cost estimator calibration
confidence calibration
benchmark trend
policy violations
context drift
```

### 11.2 Health dashboard

```text
Runtime Health: 91%

KG freshness: 96%
Memory quality: 88%
Skill catalog: 100%
Harnesses: 92%
Cost calibration: 74%
Confidence calibration: 81%
```

### 11.3 Doctor

```bash
opencontext doctor --runtime
```

---

## 12. Organization Intelligence

### 12.1 Objective

Extend KG beyond code:

```text
services
teams
owners
incidents
SLOs
repos
packages
deployments
runbooks
decisions
```

### 12.2 Org graph nodes

```text
Team
Person
Service
Repo
Package
System
Incident
Runbook
SLO
Deployment
Decision
Risk
```

### 12.3 Use cases

- escalation to owner;
- risk-aware workflow selection;
- change impact by service;
- prior incidents linked to code;
- policy enforcement by service criticality.

### 12.4 Sources

- CODEOWNERS;
- GitHub teams;
- Slack/Linear/Jira optional;
- incident reports;
- docs;
- OpenContext memory.

---

## 13. Policy Runtime

### 13.1 Policy DSL

```yaml
policies:
  auth:
    workflow: sdd
    security_review: required
    approval: required

  billing:
    auto_apply: false
    owner_approval: required

  token_budget:
    default: 12000
    ask_over: 20000

  destructive:
    forbidden_paths:
      - migrations/destructive/
      - secrets/
```

### 13.2 PolicyDecision

```python
class PolicyDecision(BaseModel):
    operation: str
    decision: Literal["allow", "deny", "ask", "warn"]
    reason: str
    policy_id: str
    evidence_refs: list[str]
```

### 13.3 Audit

Every policy decision is a span/event.

---

## 14. Plugin SDK

### 14.1 Objective

Allow extensions without core modifications.

Plugin types:

```text
workflow
persona
skill
harness
kg_provider
memory_provider
policy
evaluator
benchmark
adapter
studio_panel
```

### 14.2 Manifest

```yaml
schema_version: opencontext.plugin.v1
id: acme.drupal
name: ACME Drupal Pack
version: 1.0.0
requires:
  opencontext: ">=1.0"
provides:
  skills:
    - oc-drupal-entity-api
  harnesses:
    - drupal-cacheability-inspection
  evaluators:
    - drupal-phpstan-evaluator
permissions:
  filesystem:
    read:
      - web/modules/custom/**
```

### 14.3 Safety

- plugins sandboxed by default;
- explicit permissions;
- signed plugins optional;
- private registry support.

---

## 15. OpenContext Studio

### 15.1 Objective

A visual control plane.

Views:

```text
Run Timeline
Workflow Graph
Agent/Persona Graph
KG Explorer
Context Envelope
Memory Used
Patch/Receipts
Harness Gates
Cost & Tokens
Confidence
Benchmarks
Runtime Health
Config/Profile Editor
Plugin Manager
```

### 15.2 First version

Minimal local web UI:

```bash
opencontext studio
```

Reads:

```text
.opencontext/sessions/**
.opencontext/kg/**
.opencontext/memory/**
.opencontext/benchmarks/**
```

### 15.3 UX principle

Studio must answer:

```text
What happened?
Why did it happen?
What evidence supports it?
What did it cost?
What should I do next?
How can I improve the runtime?
```

---

## 16. Integration with SDD and OC Flow

### 16.1 SDD

Runtime Intelligence improves SDD by:

- estimating cost before full formal workflow;
- checking whether SDD is justified;
- profiling spec/design/tasks phases;
- benchmarking phase-level outputs;
- evolving prompts/harnesses for spec/design/task generation.

### 16.2 OC Flow

Runtime Intelligence improves OC Flow by:

- deciding if quick/fast/full lane;
- stopping low-confidence mutation;
- switching to SDD if blast radius grows;
- controlling diagnosis token burn;
- learning from repeated bugfixes.

---

## 17. Configuration

```yaml
runtime_intelligence:
  enabled: true

  observability:
    traces: true
    events: true
    otlp_export: false
    evidence_tracing: true

  cost:
    estimate_before_run: true
    show_what_if: true
    track_actual: true
    token_savings_attribution: true

  confidence:
    enabled: true
    ask_below: 0.65
    deep_mode_below: 0.75
    switch_workflow_below: 0.55

  simulator:
    enabled: true
    run_for_auto_workflow: true

  evolution:
    enabled: true
    mode: propose_only
    require_benchmarks: true
    require_approval: true

  benchmarks:
    enabled: true
    first_run_suite: true
    run_on_runtime_changes: true

  studio:
    enabled: true
    local_only: true

  plugins:
    enabled: true
    allow_unsigned: false
```

---

## 18. Roadmap

### PR R1 — Observability core

- trace/span/event models;
- evidence refs;
- JSONL exporter;
- OTLP optional.

### PR R2 — Cost Engine

- pre-run estimate;
- post-run accounting;
- what-if workflow comparison.

### PR R3 — Confidence Engine

- dimension scoring;
- thresholds;
- actions.

### PR R4 — Runtime Simulator

- dry-run simulation;
- workflow recommendation;
- risk/cost preview.

### PR R5 — Benchmark System

- task schema;
- first-run suite;
- workflow/skill/harness benchmarks.

### PR R6 — Runtime Profiler

- cost by component;
- bottleneck detection;
- recommendations.

### PR R7 — Evolution Engine

- candidates;
- benchmark gates;
- propose-only mode;
- promotion workflow.

### PR R8 — Organization Graph

- teams/services/incidents;
- owner resolver integration;
- risk-aware workflow selection.

### PR R9 — Policy Runtime

- policy DSL;
- enforcement;
- audit trail.

### PR R10 — Plugin SDK

- manifest;
- extension points;
- sandbox/permissions.

### PR R11 — OpenContext Studio MVP

- local dashboard;
- timeline;
- KG/context/memory/cost/confidence views.

---

## 19. Definition of Done

This pillar is complete when:

- every run has trace/span/evidence records;
- user can see estimated cost before execution;
- user can compare SDD vs OC Flow cost/risk;
- confidence is calculated and affects runtime decisions;
- simulator can dry-run workflow selection;
- benchmarks run for runtime changes;
- evolution engine proposes improvements but does not auto-apply unsafe changes;
- Studio visualizes workflow, context, memory, cost, confidence and artifacts;
- plugins can add skills/harnesses/evaluators without touching core;
- policies are enforced as runtime decisions, not prompt suggestions.

---

## 20. Final product vision

When all four pillars exist, OpenContext becomes:

```text
Agentic Runtime
+ Skill Ecosystem
+ Cognitive Runtime
+ Runtime Intelligence
```

The user experience becomes:

```text
OpenContext knows the repo.
OpenContext chooses the right workflow.
OpenContext estimates cost and risk.
OpenContext retrieves only needed context.
OpenContext runs the right harnesses.
OpenContext verifies locally.
OpenContext learns from outcomes.
OpenContext proposes improvements with benchmarks.
OpenContext explains everything in Studio.
```

That is the point where the product is not just “another coding agent harness”, but a serious engineering operating system for agentic development.
