# OpenContext Cognitive Runtime v1 — Knowledge Graph, Memory, Compression & Harnesses

**Documento complementario al blueprint principal:** `OpenContext Agentic Runtime v4 — SDD + OC Flow con calidad tipo Gentle AI`  
**Ámbito:** Knowledge Graph, memoria, compresión semántica, context engineering, harnesses, observabilidad y evaluación.  
**Objetivo:** diseñar la capa cognitiva de OpenContext para que SDD y OC Flow funcionen con menos tokens, más precisión, mejor recuperación de contexto y harnesses comparables a los mejores sistemas actuales de coding agents.

---

## 0. Resumen ejecutivo

OpenContext debe diferenciarse de otros runtimes agentic por una idea central:

> El agente no debe “leer el repo”. Debe consultar una representación viva, comprimida, temporal y verificable del conocimiento del proyecto.

La arquitectura final debe integrar:

```text
Knowledge Graph estructural de código
+ Knowledge Graph temporal de hechos y decisiones
+ Memoria episódica/semántica/procedimental
+ Compresión semántica gobernada
+ Harnesses observables y evaluables
+ Context retrieval con presupuesto explícito
+ Consolidación post-run
```

El objetivo operativo:

```text
first install
  -> index project
  -> create KG and context routers
  -> run first task
  -> retrieve only needed context
  -> mutate surgically
  -> inspect locally
  -> diagnose if needed
  -> consolidate useful knowledge
```

---

## 1. Mercado y estado del arte revisado

### 1.1 Zep / Graphiti

Zep propone una memoria de agente basada en un **grafo temporal**. Su componente Graphiti sintetiza datos conversacionales y datos estructurados, manteniendo relaciones históricas y permitiendo razonamiento temporal. El paper reporta mejoras en Deep Memory Retrieval y LongMemEval, además de menor latencia frente a baselines en escenarios de memoria empresarial.

**Lección para OpenContext:**

No basta con guardar “hechos”. Hay que guardar:

- cuándo fueron ciertos;
- de dónde vienen;
- si siguen vigentes;
- si sustituyen a otro hecho;
- qué run los produjo;
- qué evidencia los soporta.

### 1.2 mem0

mem0 prioriza eficiencia y memoria larga escalable. Sus resultados reportan menor latencia y ahorro de tokens frente a full-context, con variantes vectoriales y de graph memory.

**Lección para OpenContext:**

No todo debe ir al grafo. Para primera instalación y bajo coste, hace falta una memoria eficiente:

- vector/semantic memory para recall rápido;
- graph memory solo cuando aporta relaciones;
- promoción selectiva de memoria;
- políticas de coste.

### 1.3 GraphRAG

GraphRAG introdujo una forma práctica de recuperar información usando entidades y relaciones, especialmente en corpora privados narrativos.

**Lección para OpenContext:**

El contexto debe recuperarse como subgrafo, no como lista plana de archivos. Para código, esto significa:

- símbolos;
- llamadas;
- imports;
- tests relacionados;
- ownership;
- cambios recientes;
- decisiones arquitectónicas;
- riesgos.

### 1.4 Codebase-Memory / Tree-Sitter KG

Los enfoques recientes de KG estructural de código via Tree-Sitter muestran que un grafo persistente de código puede reducir drásticamente tokens y tool calls frente a exploración repetida de archivos, manteniendo calidad razonable.

**Lección para OpenContext:**

El KG de OpenContext debe ser código-nativo:

- parseo multi-lenguaje;
- símbolos;
- call graph;
- import graph;
- test graph;
- ownership graph;
- impact analysis;
- comunidades/componentes;
- MCP-first.

### 1.5 SWE-agent y Agent-Computer Interface

SWE-agent demostró que la interfaz agente-computadora importa mucho. No es solo el modelo: el harness, comandos disponibles, edición, navegación y ejecución de tests impactan el rendimiento.

**Lección para OpenContext:**

Los harnesses deben tratarse como producto principal:

- herramientas adaptadas al agente;
- outputs compactos;
- edición segura;
- test execution clara;
- patch extraction;
- stateful workspace;
- rollback.

### 1.6 Claw-SWE-Bench y harness comparability

Claw-SWE-Bench subraya que el diseño del adapter/harness puede cambiar mucho el Pass@1 incluso con el mismo modelo, y que hay que medir coste junto con rendimiento.

**Lección para OpenContext:**

OpenContext debe medir:

- tokens;
- coste;
- tool calls;
- patch size;
- success rate;
- retries;
- harness choice;
- workflow choice.

### 1.7 Agentic Harness Engineering

El trabajo reciente sobre evolución automática de harnesses destaca tres pilares: observabilidad de componentes, observabilidad de experiencia y observabilidad de decisiones. Las mejoras vienen más de tools, middleware y memoria que de prompts.

**Lección para OpenContext:**

El sistema debe guardar evidencia para mejorar harnesses:

- qué componente falló;
- qué decisión tomó;
- qué predijo;
- qué resultado tuvo;
- qué cambio de harness se propone;
- cómo revertirlo.

---

## 2. Principios para OpenContext

### 2.1 KG primero, archivos después

Regla:

```text
Search KG/signatures first.
Open files only when evidence says they are needed.
```

### 2.2 Memoria selectiva, no acumulativa

No guardar todo. Guardar solo:

- decisiones duraderas;
- convenciones;
- patrones de fallo;
- comandos de validación;
- owners;
- constraints;
- lecciones verificadas.

### 2.3 Compresión semántica, no resumen genérico

No queremos:

```text
"El agente intentó varias cosas y falló."
```

Queremos:

```text
Attempt 1 failed because checksum mismatch.
Attempt 2 failed because artifact rehydration was missing.
Constraint learned: do not skip artifact carry-over on resume.
Next viable strategy: load SessionStore before phase skip.
```

### 2.4 Harnesses como componentes evaluables

Un harness debe tener:

- inputs;
- outputs;
- gates;
- metrics;
- owner;
- version;
- failure modes;
- benchmarks.

### 2.5 First-run defaults

En primera instalación:

- no requerir configuración compleja;
- indexar de forma segura;
- detectar capabilities;
- crear context routers mínimos;
- usar context retrieval quirúrgico;
- producir resumen útil.

---

## 3. Arquitectura cognitiva final

```text
OpenContext Cognitive Runtime
│
├── Knowledge Graph
│   ├── Code Graph
│   ├── Test Graph
│   ├── Ownership Graph
│   ├── Decision Graph
│   ├── Temporal Fact Graph
│   └── Runtime Experience Graph
│
├── Memory
│   ├── Episodic Memory
│   ├── Semantic Memory
│   ├── Procedural Memory
│   ├── Project Memory
│   ├── Failure Pattern Memory
│   └── Harness Experience Memory
│
├── Compression
│   ├── Context Compressor
│   ├── Conversation Compressor
│   ├── Failure Compressor
│   ├── Artifact Compressor
│   ├── KG Summarizer
│   └── Semantic GC
│
├── Context Retrieval
│   ├── Query Planner
│   ├── Subgraph Retriever
│   ├── Path Navigator
│   ├── Evidence Curator
│   └── Budget Controller
│
├── Harness System
│   ├── Context Harness
│   ├── Planning Harness
│   ├── Mutation Harness
│   ├── Inspection Harness
│   ├── Diagnosis Harness
│   ├── Review Harness
│   ├── Security Harness
│   ├── Escalation Harness
│   └── Consolidation Harness
│
└── Evaluation
    ├── First-run benchmarks
    ├── Workflow benchmarks
    ├── Harness benchmarks
    ├── Memory benchmarks
    └── Token/cost dashboards
```

---

## 4. Knowledge Graph v2

### 4.1 Objetivo

El KG debe responder preguntas que hoy hacen gastar miles de tokens:

```text
¿Qué símbolos toca esta tarea?
¿Qué tests cubren este código?
¿Qué depende de este método?
¿Qué owners tiene este módulo?
¿Qué decisiones arquitectónicas previas afectan aquí?
¿Qué falló la última vez que tocamos esto?
¿Qué contexto mínimo necesita el builder?
```

### 4.2 Tipos de nodos

```python
class KgNodeType(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMBOL = "symbol"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    INTERFACE = "interface"
    MODULE = "module"
    PACKAGE = "package"
    TEST = "test"
    COMMAND = "command"
    CONFIG = "config"
    OWNER = "owner"
    TEAM = "team"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    FAILURE_PATTERN = "failure_pattern"
    RUN = "run"
    SESSION = "session"
    ARTIFACT = "artifact"
    SKILL = "skill"
    PERSONA = "persona"
    HARNESS = "harness"
```

### 4.3 Tipos de relaciones

```python
class KgEdgeType(StrEnum):
    CONTAINS = "contains"
    DEFINES = "defines"
    IMPORTS = "imports"
    CALLS = "calls"
    REFERENCES = "references"
    TESTS = "tests"
    COVERS = "covers"
    OWNS = "owns"
    DEPENDS_ON = "depends_on"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    CONFIGURES = "configures"
    CHANGED_BY = "changed_by"
    PRODUCED_BY = "produced_by"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    FAILED_WITH = "failed_with"
    FIXED_BY = "fixed_by"
    USED_SKILL = "used_skill"
    USED_HARNESS = "used_harness"
```

### 4.4 Temporal properties

Inspirado en Graphiti, cada nodo/hecho importante debe tener temporalidad:

```python
class TemporalMetadata(BaseModel):
    valid_from: datetime | None
    valid_to: datetime | None
    observed_at: datetime
    superseded_by: str | None
    confidence: float
    provenance: list[EvidenceRef]
```

Uso:

- decisión antigua sustituida;
- owner cambiado;
- comando de test obsoleto;
- fallo recurrente resuelto;
- API modificada.

### 4.5 EvidenceRef

```python
class EvidenceRef(BaseModel):
    source_type: Literal["file", "run", "commit", "test", "user", "memory", "artifact"]
    source_id: str
    path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    run_id: str | None = None
    confidence: float = 1.0
```

### 4.6 Graph partitions

El KG debe dividirse:

```text
structural_code_graph
test_graph
ownership_graph
decision_graph
runtime_experience_graph
memory_graph
```

Esto evita mezclar:

- hechos objetivos del código;
- inferencias;
- recuerdos;
- outputs de agentes.

---

## 5. Indexación

### 5.1 Pipeline

```text
DISCOVER
  -> PARSE
  -> EXTRACT SYMBOLS
  -> EXTRACT EDGES
  -> EXTRACT TEST LINKS
  -> EXTRACT OWNERS
  -> EXTRACT CONFIG
  -> EMBED SUMMARIES
  -> BUILD COMMUNITIES
  -> WRITE KG
  -> VALIDATE
```

### 5.2 Tree-Sitter

Usar Tree-Sitter o parsers específicos como capa principal multi-lenguaje.

Prioridad inicial:

- Python;
- TypeScript/JavaScript;
- PHP;
- YAML/JSON/TOML;
- Markdown.

Para Drupal/Symfony/PHP:

- services.yml;
- routing.yml;
- plugin annotations/attributes;
- event subscribers;
- composer.json;
- phpunit.xml;
- phpcs.xml;
- phpstan.neon.

### 5.3 Incremental indexing

No reindexar todo siempre.

```python
class IndexDelta(BaseModel):
    changed_files: list[str]
    deleted_files: list[str]
    added_files: list[str]
    affected_symbols: list[str]
    affected_edges: list[str]
```

Triggers:

- git diff;
- file mtime;
- post-run consolidation;
- manual `opencontext index`.

### 5.4 First-run index modes

```yaml
kg:
  index:
    mode: auto # minimal|balanced|deep|auto
```

#### minimal

- files;
- symbols;
- imports.

#### balanced

Default:

- files;
- symbols;
- imports;
- calls where cheap;
- tests;
- owners;
- commands;
- summaries.

#### deep

- call graph;
- type graph;
- community detection;
- ownership inference;
- architecture health.

---

## 6. Query planner

### 6.1 Problema

Un agente suele sobre-recuperar contexto. OpenContext debe planificar la consulta al KG.

### 6.2 QueryPlanner

```python
class ContextQueryPlanner:
    def plan(self, task: str, workflow: str, node: str, budget: ContextBudget) -> ContextQueryPlan:
        ...
```

### 6.3 Plan

```python
class ContextQueryPlan(BaseModel):
    task: str
    workflow: str
    node: str
    intent: str
    seed_terms: list[str]
    target_node_types: list[KgNodeType]
    expansion_policy: ExpansionPolicy
    stop_policy: StopPolicy
    budget: ContextBudget
```

### 6.4 Expansion policies

```text
symbol_first
test_first
owner_first
recent_failure_first
callers_callees
architecture_boundary
```

### 6.5 Stop policies

Stop when:

- acceptance criteria covered;
- enough direct evidence;
- token budget reached;
- expansion adds low novelty;
- risk requires user escalation.

---

## 7. Subgraph retrieval

### 7.1 SubgraphRetriever

```python
class SubgraphRetriever:
    def retrieve(self, plan: ContextQueryPlan) -> ContextSubgraph:
        ...
```

### 7.2 ContextSubgraph

```python
class ContextSubgraph(BaseModel):
    nodes: list[KgNode]
    edges: list[KgEdge]
    evidence: list[EvidenceRef]
    omitted: list[Omission]
    token_estimate: int
    confidence: float
```

### 7.3 Retrieval tiers

```text
Tier A: exact symbol/file/test hits
Tier B: callers/callees/importers/tests
Tier C: owners/decisions/failures
Tier D: snippets/full files only if needed
```

### 7.4 Default budget

| Workflow | Node | Budget |
|---|---|---:|
| OC Flow | gather_context | 2500-4500 |
| OC Flow | mutate | 1500-3000 |
| OC Flow | diagnose | 2000-4000 |
| SDD | explore | 6000-12000 |
| SDD | design | 4000-8000 |
| SDD | apply | 3000-6000 |
| SDD | verify | mostly local |

---

## 8. Memory v2

### 8.1 Memory taxonomy

```text
Episodic Memory
  -> what happened in runs/sessions

Semantic Memory
  -> durable facts about project

Procedural Memory
  -> how to do things in this repo

Failure Pattern Memory
  -> recurring failures and fixes

Preference/Policy Memory
  -> user/team preferences and constraints

Harness Experience Memory
  -> harness decisions and outcomes
```

### 8.2 MemoryRecord

```python
class MemoryRecord(BaseModel):
    schema_version: str = "opencontext.memory.v2"
    id: str
    kind: MemoryKind
    content: str
    structured: dict[str, Any]
    tags: list[str]
    scope: Literal["project", "repo", "workspace", "user", "team"]
    confidence: float
    source: EvidenceRef
    created_at: datetime
    last_seen_at: datetime
    valid_from: datetime | None
    valid_to: datetime | None
    supersedes: list[str] = []
    status: Literal["active", "stale", "superseded", "rejected"]
```

### 8.3 What to save

Save:

- commands that worked;
- test command discovery;
- architecture decisions;
- conventions;
- owner mappings;
- failure patterns;
- high-confidence constraints;
- accepted tradeoffs;
- repeated context routing.

Do not save:

- chain-of-thought;
- raw chat logs;
- whole source files;
- long stack traces;
- failed code attempts;
- one-off guesses;
- secrets.

### 8.4 Memory promotion

Not every run output becomes durable memory.

Pipeline:

```text
candidate
  -> classify
  -> deduplicate
  -> verify evidence
  -> assign confidence
  -> store episodic
  -> promote to semantic/procedural only if durable
```

### 8.5 Memory retrieval

Memory retrieval should be cheap-first:

```text
keyword/tag lookup
  -> vector similarity
  -> graph neighborhood
  -> temporal filter
  -> confidence ranking
```

### 8.6 Memory conflict resolution

If a new memory contradicts old memory:

- do not overwrite silently;
- create `CONTRADICTS` edge;
- mark old as stale if evidence stronger;
- surface if both plausible.

---

## 9. Project Memory files

OpenContext should support human-readable memory files.

```text
.opencontext/memory/
  project-profile.md
  conventions.md
  decisions.md
  commands.md
  failure-patterns.md
  owners.md
  environment.md
  harness-learnings.md
```

These are not the full memory database; they are curated summaries.

### 9.1 commands.md

```md
# Commands

## Tests
- Unit: `pytest tests/unit`
- PHPStan: `vendor/bin/phpstan analyse`
- PHPCS: `vendor/bin/phpcs`

## Notes
- `pytest` must run with `PYTHONPATH=packages/opencontext_core`.
```

### 9.2 failure-patterns.md

```md
# Failure Patterns

## Session resume skips artifacts
Evidence: run ocf-123
Symptom: phase skipped but prior artifact not rehydrated
Fix: load artifact carry-over before phase skip
Status: active
```

---

## 10. Compression v2

### 10.1 Compression targets

```text
conversation
context
failure logs
test outputs
KG neighborhoods
memory
artifacts
run summaries
```

### 10.2 Compression is not summarization

Compression must preserve:

- constraints;
- decisions;
- evidence;
- failed strategies;
- current error;
- next action;
- risk flags;
- provenance.

### 10.3 ContextCompressor

```python
class ContextCompressor:
    def compress_context(self, envelope: ContextEnvelope, budget: int) -> CompressedContext:
        ...
```

Strategies:

- keep signatures;
- drop implementation;
- keep changed lines;
- keep public contracts;
- keep tests;
- keep errors;
- keep owners;
- drop low-confidence memories.

### 10.4 FailureCompressor

After repeated failures:

```python
class FailureCompressor:
    def compress(self, attempts: list[DiagnosisAttempt]) -> FailureSummary:
        ...
```

Output:

```json
{
  "failed_strategies": [
    "Re-ran verify without rehydrating artifacts"
  ],
  "constraints_learned": [
    "Resume must load prior artifact refs before phase skip"
  ],
  "current_error": "...",
  "next_viable_strategy": "...",
  "do_not_repeat": ["..."]
}
```

### 10.5 Semantic GC

Runs:

- after successful inspection;
- after two failed diagnosis attempts;
- at consolidation;
- before session resume;
- before archive.

Deletes or demotes:

- duplicate logs;
- low-confidence inferred memories;
- stale L1 context;
- obsolete context snippets.

Keeps:

- L2 task contract;
- final receipts;
- final error if escalated;
- memory candidates;
- gate outcomes.

### 10.6 Compression budget policies

```yaml
compression:
  mode: balanced
  max_context_tokens:
    oc_flow: 6500
    sdd: 18000
  failure_gc_after_attempts: 2
  preserve_evidence: true
```

---

## 11. Harnesses v2

### 11.1 Harness definition

```python
class HarnessDefinition(BaseModel):
    id: str
    version: str
    type: HarnessType
    description: str
    inputs: list[str]
    outputs: list[str]
    required_capabilities: list[str]
    gates: list[str]
    token_cost: Literal["zero", "low", "medium", "high"]
    default_mode: Literal["off", "warn", "strict"]
    metrics: list[str]
```

### 11.2 Harness registry

```text
harnesses/
  context/
  planning/
  mutation/
  inspection/
  diagnosis/
  review/
  security/
  escalation/
  consolidation/
  memory/
  kg/
  evaluation/
```

### 11.3 Context Harness

Responsibilities:

- intent-aware KG retrieval;
- context envelope;
- budget enforcement;
- evidence preservation;
- omissions.

Gates:

- `context_envelope_created`
- `included_sources_present`
- `omissions_recorded`
- `token_budget_respected`
- `kg_fallback_recorded`

### 11.4 Planning Harness

Responsibilities:

- SDD spec/design/tasks validation;
- OC Flow task contract;
- no code in planning;
- acceptance criteria.

Gates:

- `acceptance_criteria_present`
- `requirements_falsifiable`
- `plan_references_context`
- `no_business_code_in_plan`

### 11.5 Mutation Harness

Responsibilities:

- path policy;
- ApplyEdit;
- checksum;
- patch;
- rollback;
- receipts.

Gates:

- `apply_receipts_created`
- `patch_created`
- `forbidden_paths_clean`
- `checksum_verified`
- `rollback_available`

### 11.6 Inspection Harness

Responsibilities:

- syntax;
- AST guards;
- secrets;
- lint;
- typecheck;
- targeted tests;
- broad tests.

Gates:

- `syntax_valid`
- `no_secret_leakage`
- `quality_standards`
- `tests_pass`
- `srp_guard`
- `dip_guard`

### 11.7 Diagnosis Harness

Responsibilities:

- reproduce;
- hypotheses;
- instrumentation;
- fix;
- anti-repeat;
- compression;
- escalation.

Gates:

- `reproduction_recorded`
- `hypothesis_count_valid`
- `selected_hypothesis_has_evidence`
- `failed_strategy_not_repeated`
- `attempt_budget_respected`

### 11.8 Review Harness

Responsibilities:

- grounded review;
- severity;
- no praise-only output;
- changed-scope focus;
- architecture regression.

Gates:

- `review_artifact_created`
- `findings_grounded`
- `severity_present`
- `no_unverified_claims`

### 11.9 Security Harness

Responsibilities:

- secret scan;
- trust boundary;
- injection risk;
- network/export risk;
- auth/billing/public API.

Gates:

- `no_secret_leakage`
- `network_policy_passed`
- `trust_boundary_reviewed`
- `no_high_risk_exports`

### 11.10 Memory Harness

Responsibilities:

- memory candidate extraction;
- promotion;
- dedup;
- conflict detection;
- project memory update.

Gates:

- `memory_delta_created`
- `memory_candidates_classified`
- `no_raw_cot_saved`
- `stale_memory_marked`

### 11.11 KG Harness

Responsibilities:

- incremental reindex;
- graph delta;
- changed symbol update;
- decision/failure edges.

Gates:

- `graph_delta_created`
- `changed_symbols_reindexed`
- `owners_resolved_or_recorded_unknown`
- `kg_consistency_check_passed`

### 11.12 Evaluation Harness

Responsibilities:

- benchmark run;
- metrics;
- harness decision evaluation;
- prediction vs outcome.

Gates:

- `metrics_recorded`
- `cost_recorded`
- `decision_outcome_linked`

---

## 12. Harness matrix for SDD and OC Flow

### 12.1 SDD

| Harness | Mode |
|---|---|
| Context | strict |
| Planning | strict |
| Mutation | strict |
| Inspection | warn/strict by profile |
| Diagnosis | optional |
| Review | strict |
| Security | conditional |
| Memory | strict |
| KG | strict |
| Evaluation | warn |

### 12.2 OC Flow

| Harness | Mode |
|---|---|
| Context | strict |
| Planning | strict-lite |
| Mutation | strict |
| Inspection | strict |
| Diagnosis | strict |
| Review | optional |
| Security | conditional |
| Memory | strict |
| KG | strict |
| Evaluation | warn |

---

## 13. Harness observability

### 13.1 Component observability

Each harness component must be represented as:

```json
{
  "component_id": "inspection.local_first",
  "version": "1.0.0",
  "inputs": [],
  "outputs": [],
  "config_hash": "...",
  "owner": "opencontext"
}
```

### 13.2 Experience observability

Store compressed trajectory:

```json
{
  "run_id": "...",
  "workflow": "oc-flow",
  "task_type": "bugfix",
  "context_tokens": 3200,
  "tool_calls": 12,
  "mutation_count": 2,
  "tests_run": 1,
  "success": true,
  "failure_patterns": []
}
```

### 13.3 Decision observability

When harness makes a decision:

```json
{
  "decision_id": "...",
  "component": "workflow.selector",
  "decision": "oc-flow",
  "prediction": "localized bugfix; low blast radius; expected one mutation",
  "outcome": "success",
  "cost": {
    "tokens": 5400,
    "tool_calls": 9
  }
}
```

This supports future harness evolution.

---

## 14. Evaluation and benchmarks

### 14.1 First-run benchmark

Tasks:

- Python failing test;
- TypeScript lint error;
- PHP/Drupal service bug;
- documentation update;
- small feature requiring SDD.

Metrics:

- success;
- tokens;
- time;
- tool calls;
- changed lines;
- patch correctness;
- no scope creep;
- summary quality.

### 14.2 Memory benchmark

Measure:

- did memory retrieve correct command?
- did it avoid stale memory?
- did it detect contradiction?
- did it save useful failure pattern?

### 14.3 KG benchmark

Measure:

- symbol lookup accuracy;
- caller/callee accuracy;
- test link accuracy;
- owner accuracy;
- token reduction vs file exploration.

### 14.4 Harness benchmark

Measure:

- workflow selector correctness;
- context harness token savings;
- diagnosis convergence;
- inspection catch rate;
- rollback success.

---

## 15. Configuration

### 15.1 Main config

```yaml
cognitive:
  kg:
    enabled: true
    mode: balanced
    temporal: true
    index:
      incremental: true
      max_files_first_run: 5000
      parsers:
        tree_sitter: true
    retrieval:
      default_strategy: surgical_subgraph
      max_expansion_hops: 2
      full_file_fallback: ask

  memory:
    enabled: true
    mode: balanced
    episodic: true
    semantic: true
    procedural: true
    failure_patterns: true
    temporal_validity: true
    promotion_policy: evidence_based

  compression:
    enabled: true
    mode: semantic
    failure_gc_after_attempts: 2
    preserve_evidence: true
    max_context_tokens:
      oc_flow: 6500
      sdd: 18000

  harnesses:
    context: strict
    planning: workflow_default
    mutation: strict
    inspection: strict
    diagnosis: workflow_default
    review: workflow_default
    security: conditional
    memory: strict
    kg: strict

  evaluation:
    record_metrics: true
    record_decisions: true
    benchmark_on_ci: false
```

### 15.2 Profiles

#### balanced

Default.

```yaml
kg.mode: balanced
memory.mode: balanced
compression.mode: semantic
harnesses.inspection: strict
```

#### low-cost

```yaml
kg.retrieval.max_expansion_hops: 1
memory.graph: false
compression.max_context_tokens.oc_flow: 3500
diagnosis.max_attempts: 1
```

#### enterprise

```yaml
kg.mode: deep
kg.temporal: true
memory.conflict_detection: strict
harnesses.security: strict
observability.opentelemetry: true
evaluation.record_decisions: true
```

---

## 16. Roadmap

### PR C1 — KG schema v2

- node/edge types;
- temporal metadata;
- evidence refs;
- partitions.

### PR C2 — Incremental indexer

- file/symbol graph;
- imports;
- tests;
- owners;
- config extraction.

### PR C3 — Context retrieval planner

- query planner;
- subgraph retriever;
- budget controller;
- context envelope.

### PR C4 — Memory v2

- memory taxonomy;
- memory records;
- promotion policy;
- conflict detection.

### PR C5 — Project memory files

- decisions;
- conventions;
- commands;
- failure patterns;
- owners.

### PR C6 — Compression engine

- context compressor;
- failure compressor;
- semantic GC;
- compression receipts.

### PR C7 — Harness registry

- definitions;
- modes;
- gates;
- workflow matrix.

### PR C8 — Harness observability

- component metadata;
- decision records;
- experience summaries.

### PR C9 — Evaluation harness

- first-run benchmarks;
- KG benchmark;
- memory benchmark;
- harness benchmark.

### PR C10 — Consolidation pipeline

- post-run memory harvest;
- KG delta;
- context refresh;
- stale memory handling.

---

## 17. Definition of Done

This plan is complete when:

- first-run indexing creates a useful KG;
- KG retrieval avoids broad file dumps by default;
- OC Flow can complete a bugfix with subgraph context;
- SDD explore produces structured context envelopes;
- memory saves useful durable facts only;
- failure compression prevents repeated strategies;
- harnesses are registry-defined and observable;
- every mutation has KG/memory consolidation;
- benchmarks track tokens and success;
- stale/contradictory memory can be detected;
- user-facing summaries explain what context was used and why.

---

## 18. Final architecture statement

OpenContext should become the system that gives agents:

```text
not more context,
but the right context;

not more memory,
but useful memory;

not more retries,
but better diagnosis;

not more prompts,
but stronger harnesses.
```

The Cognitive Runtime is the layer that makes SDD and OC Flow reliable, efficient and explainable.
