# OpenContext Agentic Runtime v4 — Plan hiperexhaustivo para SDD + OC Flow con calidad tipo Gentle AI

**Rama objetivo:** `feat/agentic-engineering-runtime`  
**Objetivo de producto:** tras instalar OpenContext por primera vez, el usuario debe poder ejecutar una primera tarea real con alta probabilidad de éxito, bajo consumo de tokens, trazabilidad completa y comportamiento de harness/personas/skills comparable a sistemas agentic modernos tipo Gentle AI.

Este documento reemplaza y consolida los blueprints anteriores. La conclusión arquitectónica definitiva es:

> **No se reemplaza SDD. Se corrige y se eleva hasta un SDD agentic con harnesses correctos. Se añade OC Flow como workflow operativo paralelo. Ambos workflows comparten el mismo Runtime, Harness Registry, Persona Registry, Skill Registry, Capability Registry, Policy Engine, Memory, Knowledge Graph, Event Bus, Telemetry y UX Configuration.**

---

## 0. Criterio de aceptación principal

Este plan no se considera terminado cuando “compila” o cuando “hay nuevas clases”.

Se considera terminado cuando una instalación limpia cumple esto:

```bash
pipx install opencontext-cli
cd my-project
opencontext init --profile balanced
opencontext index
opencontext run "Fix the failing test around session resume" --workflow auto
```

y el sistema:

1. Detecta capacidades del proyecto.
2. Selecciona `oc-flow` si es bugfix localizado o `sdd` si es cambio formal.
3. Construye contexto quirúrgico, no un dump de archivos.
4. Usa persona correcta.
5. Usa skills correctas.
6. Aplica mutaciones pequeñas con receipts.
7. Ejecuta inspección local antes de gastar más tokens.
8. Diagnostica de forma metódica si falla.
9. No repite estrategias fallidas.
10. Escala si no converge.
11. Devuelve un resumen útil con patch, artifacts, gates y next action.
12. No exige que el usuario entienda toda la configuración para que funcione.

---

## 1. Principio rector: primera tarea bien hecha

El diseño debe optimizar para la primera experiencia:

```text
first install -> first index -> first task -> useful result
```

No para “máxima configurabilidad teórica”.

La configuración avanzada debe existir, pero los defaults deben ser buenos.

### 1.1 Default esperado

```yaml
profile: balanced
workflow:
  default: auto
runtime:
  mode: run_to_completion
context:
  strategy: surgical_first
inspection:
  local_first: true
diagnostics:
  enabled: true
  max_attempts: 2
policies:
  auto_apply: ask_if_risky
  network: deny_by_default
observability:
  live_state: true
```

### 1.2 Resultado esperado de una primera tarea

Un usuario no debería ver solo:

```json
{"status": "passed", "artifacts": 8}
```

Debe ver:

```text
Workflow selected: oc-flow
Reason: localized bugfix with existing failing test

Changed:
- packages/opencontext_core/opencontext_core/runtime/session_store.py

Verified:
- syntax: passed
- unit tests: passed
- secrets: passed
- code economy: warning

Artifacts:
- patch.diff
- apply-receipts.json
- inspection-report.json
- run-summary.md

Next:
Review patch.diff, then commit.
```

---

## 2. Diagnóstico de la rama actual

La rama ya tiene una base importante, pero todavía no alcanza el estándar deseado de “primera tarea bien hecha”.

### 2.1 Fortalezas existentes

#### MCP con envelopes y schemas

El servidor MCP ya tiene herramientas, output schemas permisivos y `ToolResultEnvelope`. Esto es una buena base para UX y trazabilidad.

#### HarnessRunner con fases SDD

El runner ya tiene:

- `HarnessState`;
- budgets;
- gates;
- artifacts;
- decisions;
- warnings;
- context pack;
- apply edits;
- approved phases;
- delegate;
- context sources;
- architecture baseline;
- post-run reindex.

#### Personas existentes

Ya existen varias personas útiles:

- `oc-orchestrator`
- `oc-professor`
- `oc-reviewer`
- `oc-tester`
- `oc-explorer`
- `oc-architect`
- `oc-builder`
- `oc-context-engineer`
- `oc-requirements`
- `oc-planner`
- `oc-harness-verifier`
- `oc-archivist`
- `oc-evolution-steward`

Esto es muy valioso. No hay que sustituirlo; hay que convertirlo en un **Persona Registry gobernado** y añadir los roles que faltan.

#### Skills existentes

La capa de skills ya escanea `SKILL.md`, extrae `compact_rules` y resuelve por triggers/file patterns. Es útil, pero todavía insuficiente para garantizar calidad. Las skills son texto de prompt; deben pasar a ser **skills verificables con contratos y gates**.

#### ApplyEdit

`ApplyEdit` quirúrgico ya existe y debe convertirse en el camino principal.

#### HarnessConfig

Ya existe configuración de:

- budgets por fase;
- `gate_policy`;
- `tdd_mode`;
- `approval_required_for_writes`;
- `surgical_explore`;
- `auto_index_max_files`;
- forbidden paths;
- forbidden commands.

Esto debe integrarse en una configuración única orientada a UX.

---

## 3. Problemas que impiden funcionamiento tipo Gentle AI

### 3.1 `opencontext_run` es demasiado monolítico

Actualmente el patrón sigue siendo:

```text
tool call -> run all phases -> return summary
```

Eso dificulta:

- progreso en tiempo real;
- session resume;
- diagnóstico incremental;
- UX de first-run;
- integración con agente host;
- bajo consumo de tokens.

Solución:

- mantener `opencontext_run` como shortcut;
- crear Session Runtime incremental;
- hacer que `opencontext_run` use Session Runtime por debajo.

### 3.2 SDD no está roto conceptualmente, pero sí incompleto como harness

SDD tiene fases correctas, pero necesita:

- contratos estrictos entre fases;
- handoffs persistidos;
- real executor para `propose`;
- scaffolds tratados como planned/warning, no success;
- verify local-first;
- receipts y patches;
- resume real con artifacts;
- summaries útiles.

### 3.3 Falta OC Flow

Hace falta un flujo más rápido que SDD para tareas reales:

- bugfix;
- refactor pequeño;
- test failing;
- mejora incremental;
- cleanup;
- small feature.

### 3.4 Personas sin contrato operativo

Las personas tienen prompts buenos, pero no están gobernadas por:

- output schemas;
- allowed tools por workflow/node;
- expected artifacts;
- required skills;
- failure policy;
- token budget;
- handoff contract.

### 3.5 Skills demasiado ligeras

El resolver actual elige skills por triggers y file patterns, pero falta:

- versionado;
- skill contract;
- input/output schema;
- gates;
- examples;
- negative rules;
- max token budget;
- workflow applicability;
- persona applicability;
- language applicability;
- first-run bundle.

### 3.6 Harnesses no están formalizados como registry

Hay gates, phases y checks, pero no un registro reusable de harness components.

Debe existir:

```text
Harness Registry
  protocol
  context
  planning
  mutation
  inspection
  diagnosis
  review
  escalation
  consolidation
  receipts
```

---

## 4. Arquitectura final

```text
OpenContext
│
├── Runtime
│   ├── Session Runtime
│   ├── Workflow Engine
│   ├── State Machine
│   ├── Event Bus
│   └── Telemetry
│
├── Workflow Registry
│   ├── sdd
│   ├── oc-flow
│   ├── quick
│   ├── review
│   └── future workflows
│
├── Persona Registry
│   ├── orchestrator
│   ├── explorer
│   ├── context-engineer
│   ├── requirements
│   ├── architect
│   ├── planner
│   ├── builder
│   ├── tester
│   ├── reviewer
│   ├── diagnostician
│   ├── security-reviewer
│   ├── harness-verifier
│   ├── archivist
│   └── evolution-steward
│
├── Skill Registry
│   ├── builtin skills
│   ├── project skills
│   ├── user skills
│   ├── language skills
│   ├── framework skills
│   └── workflow bundles
│
├── Harness Registry
│   ├── context harness
│   ├── planning harness
│   ├── mutation harness
│   ├── inspection harness
│   ├── diagnosis harness
│   ├── review harness
│   ├── security harness
│   ├── escalation harness
│   └── consolidation harness
│
├── Capability Registry
│   ├── kg
│   ├── memory
│   ├── git
│   ├── terminal
│   ├── test runners
│   ├── linters
│   ├── type checkers
│   └── package managers
│
├── Policy Engine
│   ├── file policy
│   ├── command policy
│   ├── network policy
│   ├── provider policy
│   ├── secrets policy
│   └── auto-apply policy
│
├── Knowledge Graph
├── Context Layers
├── Memory
├── MCP
├── CLI
├── TUI/Dashboard
└── Config Profiles
```

---

## 5. Workflows

## 5.1 SDD Workflow

SDD se mantiene como flujo formal.

```text
explore
  -> propose
  -> spec
  -> design
  -> tasks
  -> apply
  -> verify
  -> review
  -> archive
```

### 5.1.1 Objetivo de SDD

Usar SDD cuando:

- hay feature nueva;
- hay cambio arquitectónico;
- hay cambio de API;
- afecta múltiples módulos;
- se requiere trazabilidad;
- se necesita spec/design/tasks explícito;
- usuario pide “hacerlo bien y documentado”.

### 5.1.2 SDD debe quedar como Gentle-like SDD

El SDD corregido debe tener:

- personas por fase;
- skill bundles por fase;
- context handoff controlado;
- contracts por artifact;
- verification local-first;
- receipts;
- resume real;
- review independiente;
- archive con memory harvest;
- token budgets estrictos;
- no whole-file rewrites salvo fallback;
- no scaffolds como success.

### 5.1.3 Personas en SDD

| Fase | Persona | Estado actual | Acción |
|---|---|---:|---|
| explore | oc-explorer + oc-context-engineer | existe | mantener y optimizar |
| propose | oc-orchestrator | existe, pero executor no lo registra bien | corregir |
| spec | oc-requirements | existe | mantener |
| design | oc-architect | existe | mantener |
| tasks | oc-planner | existe | mantener |
| apply | oc-builder | existe | endurecer con mutation contract |
| test | oc-tester | existe | usar cuando TDD activo |
| verify | oc-harness-verifier | existe | reforzar local-first |
| review | oc-reviewer | existe | review independiente |
| archive | oc-archivist | existe | mantener |
| evolution | oc-evolution-steward | existe | opcional post-run |

### 5.1.4 Huecos de SDD

Añadir:

- `oc-security-reviewer` para security-sensitive changes;
- `oc-diagnostician` para fix-loop opcional;
- `oc-release-steward` para release/package workflows;
- `oc-docs-writer` si SDD produce documentación pública.

No todos activos por defecto. Solo se activan por workflow/profile/capabilities.

---

## 5.2 OC Flow

OC Flow es el flujo agentic operativo.

```text
init
  -> gather_context
  -> plan
  -> mutate
  -> local_inspection
      -> consolidation        if passed
      -> diagnose             if recoverable failure
      -> escalation           if blocked/unrecoverable

diagnose
  -> mutate                   if fix ready
  -> escalation               if attempts exhausted

escalation
  -> consolidation
```

### 5.2.1 Objetivo de OC Flow

Usar OC Flow cuando:

- bugfix;
- test failing;
- refactor localizado;
- cambio pequeño;
- cleanup;
- performance local;
- error de lint/type;
- tarea de mantenimiento.

### 5.2.2 Personas en OC Flow

| Nodo | Persona | Skills |
|---|---|---|
| init | oc-orchestrator | workflow-selection, policy-prime |
| gather_context | oc-context-engineer + oc-explorer | surgical-context, kg-impact-lite |
| plan | oc-architect | task-contract-lite, no-business-code-plan |
| mutate | oc-builder | surgical-mutation, code-economy |
| local_inspection | oc-harness-verifier | local-first-inspection |
| diagnose | oc-diagnostician | reproduce-hypothesize-instrument-fix |
| escalation | oc-escalation-steward / oc-orchestrator | owner-handoff |
| consolidation | oc-archivist | memory-harvest, kg-refresh |

### 5.2.3 Nuevo rol obligatorio: OC Diagnostician

Debe añadirse porque OC Flow depende de diagnóstico metódico.

Prompt resumido:

```text
You are the OC Diagnostician.
You do not guess-patch. You reproduce, formulate exactly three hypotheses, choose one using evidence, instrument only if needed, apply the smallest fix, and never repeat a failed strategy.
```

Allowed tools:

```text
KG read tools
Memory tools
Read
Bash
Edit/Write only through controlled mutation path
```

Output schema:

```xml
<agent_response schema="opencontext.diagnosis.v1">
  <failure_summary>...</failure_summary>
  <reproduce command="...">...</reproduce>
  <hypotheses>
    <hypothesis id="H1">...</hypothesis>
    <hypothesis id="H2">...</hypothesis>
    <hypothesis id="H3">...</hypothesis>
  </hypotheses>
  <selected_hypothesis id="H2">
    <evidence>...</evidence>
  </selected_hypothesis>
  <fix_strategy>...</fix_strategy>
  <code_mutation ...>...</code_mutation>
</agent_response>
```

---

## 6. Workflow Registry

### 6.1 Objetivo

Los workflows deben estar declarados, no hardcodeados.

```text
workflow/builtins/sdd.yaml
workflow/builtins/oc-flow.yaml
workflow/builtins/quick.yaml
workflow/builtins/review.yaml
```

### 6.2 Modelo

```python
class WorkflowDefinition(BaseModel):
    schema_version: str = "opencontext.workflow.v1"
    id: str
    label: str
    description: str
    kind: Literal["formal", "operational", "review", "maintenance"]
    version: str
    default_profile: str
    nodes: dict[str, WorkflowNodeDefinition]
    edges: list[WorkflowEdge]
    start_node: str
    terminal_nodes: list[str]
    aliases: list[str] = []
    first_run_recommended: bool = False
```

### 6.3 SDD definition

SDD definition debe mapear las fases existentes y mantener aliases:

```yaml
id: sdd
aliases:
  - full
  - standard
  - quick
kind: formal
```

### 6.4 OC Flow definition

```yaml
id: oc-flow
aliases:
  - oc
  - agentic
  - fix
kind: operational
first_run_recommended: true
```

---

## 7. Workflow selector automático

### 7.1 Por qué es necesario

Para primera instalación, el usuario no sabe si usar SDD u OC Flow.

`workflow: auto` debe ser el default.

### 7.2 Selector

```python
class WorkflowSelector:
    def select(
        self,
        task: str,
        root: Path,
        capabilities: CapabilitySet,
        kg_summary: ProjectSummary,
        config: RuntimeConfig,
    ) -> WorkflowSelection:
        ...
```

### 7.3 Reglas

Seleccionar `sdd` si:

- task contiene “feature”, “design”, “architecture”, “new module”, “API”, “contract”;
- afecta varios módulos;
- KG impact > threshold;
- user asks for spec/design;
- profile enterprise/research;
- no failing test concrete;
- riesgo alto.

Seleccionar `oc-flow` si:

- task contiene “fix”, “bug”, “failing test”, “lint”, “type error”;
- cambio localizado;
- existe test/linter command;
- KG impact bajo;
- profile low-cost/performance;
- first-run demo task.

### 7.4 Respuesta

```json
{
  "selected": "oc-flow",
  "confidence": 0.86,
  "reason": "Localized bugfix with test-related wording and low KG blast radius",
  "alternative": "sdd",
  "estimated_token_budget": 6500
}
```

---

## 8. Persona Registry

### 8.1 Problema actual

Las personas están en código Python. Eso funciona, pero para UX, configuración y extensibilidad hay que registrarlas como entidades versionadas.

### 8.2 Modelo

```python
class PersonaDefinition(BaseModel):
    schema_version: str = "opencontext.persona.v1"
    id: str
    name: str
    description: str
    visibility: Literal["public_main", "public_support", "hidden_delegation"]
    default_tools: list[str]
    default_budget_tokens: int
    system_prompt: str
    output_contracts: list[str] = []
    compatible_workflows: list[str] = []
    compatible_nodes: list[str] = []
    required_skills: list[str] = []
    forbidden_behaviors: list[str] = []
```

### 8.3 Personas existentes a conservar

- `oc-orchestrator`
- `oc-professor`
- `oc-reviewer`
- `oc-tester`
- `oc-explorer`
- `oc-architect`
- `oc-builder`
- `oc-context-engineer`
- `oc-requirements`
- `oc-planner`
- `oc-harness-verifier`
- `oc-archivist`
- `oc-evolution-steward`

### 8.4 Personas nuevas necesarias

#### oc-diagnostician

Para OC Flow y fix loops opcionales en SDD.

Responsabilidad:

- reproducir;
- formular 3 hipótesis;
- instrumentar;
- corregir;
- evitar repetición.

#### oc-security-reviewer

Para cambios en auth, secrets, network, filesystem, providers, subprocess, CI/CD.

Responsabilidad:

- threat check local;
- secret handling;
- permission boundaries;
- path escape;
- command injection;
- provider exfiltration.

#### oc-release-steward

Para release/package/versioning.

Responsabilidad:

- changelog;
- packaging;
- CI publish;
- version bump;
- release verification.

#### oc-docs-writer

Para docs/README/API docs cuando workflow lo pida.

Responsabilidad:

- documentar cambios reales;
- no inventar features;
- links a artifacts;
- usage examples.

#### oc-performance-reviewer

Opcional para performance-sensitive tasks.

Responsabilidad:

- detect hot paths;
- avoid needless broad context;
- check complexity/regressions.

### 8.5 Mapping final

| Persona | SDD | OC Flow | Default |
|---|---:|---:|---:|
| Orchestrator | yes | yes | yes |
| Context Engineer | yes | yes | yes |
| Explorer | yes | yes | yes |
| Requirements | yes | optional | yes |
| Architect | yes | yes | yes |
| Planner | yes | optional | yes |
| Builder | yes | yes | yes |
| Tester | yes | yes | yes |
| Harness Verifier | yes | yes | yes |
| Reviewer | yes | optional | yes |
| Diagnostician | optional | yes | new |
| Security Reviewer | conditional | conditional | new |
| Archivist | yes | yes | yes |
| Evolution Steward | optional | optional | yes |
| Docs Writer | conditional | conditional | new |
| Release Steward | conditional | no | new |

---

## 9. Skill Registry v2

### 9.1 Problema actual

El skill registry actual:

- escanea `SKILL.md`;
- extrae frontmatter;
- extrae reglas compactas;
- resuelve por triggers;
- no impone contratos.

Esto es insuficiente para first-run quality.

### 9.2 SkillDefinition

```python
class SkillDefinition(BaseModel):
    schema_version: str = "opencontext.skill.v1"
    id: str
    name: str
    version: str
    description: str
    triggers: list[str]
    workflows: list[str]
    nodes: list[str]
    personas: list[str]
    file_patterns: list[str]
    languages: list[str]
    frameworks: list[str]
    compact_rules: list[str]
    required_outputs: list[str]
    forbidden_outputs: list[str]
    gates: list[str]
    examples: list[SkillExample] = []
    token_budget: int = 800
    priority: int = 100
```

### 9.3 Skill bundles

Un workflow no debe resolver skills sueltas sin control. Debe cargar bundles.

```yaml
skill_bundles:
  sdd_default:
    - oc-context-surgical
    - oc-requirements-rfc2119
    - oc-design-minimal
    - oc-task-splitting
    - oc-apply-surgical
    - oc-verify-local-first
    - oc-review-grounded
    - oc-archive-memory

  oc_flow_default:
    - oc-context-surgical
    - oc-plan-lite
    - oc-apply-surgical
    - oc-inspect-local-first
    - oc-diagnose-three-hypotheses
    - oc-semantic-gc
    - oc-escalate-owner
    - oc-archive-memory
```

### 9.4 Builtin skills obligatorias

#### oc-context-surgical

Reglas:

- start with `opencontext_search`;
- use KG node/code for exact symbol;
- use broad context only when needed;
- include omissions;
- prefer signatures over full files.

Gates:

- `context_pack_created`
- `included_sources_present`
- `omissions_recorded`
- `token_budget`

#### oc-plan-lite

Para OC Flow.

Reglas:

- plan must fit in task contract;
- no business code in plan;
- no broad speculation;
- max 7 steps;
- every step has verification.

Gates:

- `task_contract_created`
- `no_code_in_plan`
- `acceptance_criteria_present`

#### oc-requirements-rfc2119

Para SDD spec.

Reglas:

- MUST/SHALL/SHOULD only;
- every requirement has GIVEN/WHEN/THEN;
- no implementation details.

Gates:

- `requirements_are_falsifiable`
- `acceptance_scenarios_present`

#### oc-design-minimal

Reglas:

- reuse existing symbols before adding new;
- no abstraction without current second caller;
- design names files/components/data flow/tests;
- account for architecture health.

Gates:

- `design_references_spec`
- `code_economy`
- `architecture_clean`

#### oc-task-splitting

Reglas:

- atomic tasks;
- each task references requirement;
- each task has verification;
- split if touches too many files.

Gates:

- `tasks_reference_requirements`
- `tasks_have_verification`

#### oc-apply-surgical

Reglas:

- prefer `ApplyEdit`;
- avoid whole-file rewrite;
- include reason and requirement refs;
- no touching forbidden paths;
- compute checksum.

Gates:

- `apply_receipt_created`
- `patch_created`
- `forbidden_paths`
- `code_economy`

#### oc-inspect-local-first

Reglas:

- syntax before tests;
- AST guards before broad tests;
- secrets before any external call;
- targeted tests before full suite.

Gates:

- `syntax_valid`
- `no_secret_leakage`
- `srp_guard`
- `dip_guard`
- `tests_pass`

#### oc-diagnose-three-hypotheses

Reglas:

- reproduce before fix;
- exactly 3 hypotheses;
- choose one with evidence;
- instrument if uncertain;
- do not repeat failed strategy.

Gates:

- `reproduction_recorded`
- `hypothesis_count_is_three`
- `selected_hypothesis_has_evidence`
- `failed_strategy_not_repeated`

#### oc-semantic-gc

Reglas:

- after two failures, compress;
- preserve constraints;
- remove duplicate logs;
- keep latest actionable error.

Gates:

- `compressed_context_created`
- `failed_strategies_recorded`

#### oc-escalate-owner

Reglas:

- after attempts exhausted, stop;
- query owner;
- write handoff;
- do not spend more tokens on code.

Gates:

- `owner_resolved_or_unknown_recorded`
- `handoff_created`

#### oc-archive-memory

Reglas:

- save durable facts only;
- do not save chain-of-thought;
- save failure pattern if useful;
- reindex changed files.

Gates:

- `memory_delta_created`
- `graph_delta_created`

### 9.5 Language/framework skills

For first-run quality, detect and load:

#### Python

- `oc-python-pytest`
- `oc-python-ruff`
- `oc-python-mypy`
- `oc-python-ast-guards`

#### JavaScript/TypeScript

- `oc-js-vitest-jest`
- `oc-ts-typecheck`
- `oc-eslint`

#### PHP/Drupal/Symfony

- `oc-php-phpunit`
- `oc-phpstan`
- `oc-phpcs`
- `oc-drupal-service-container`
- `oc-drupal-plugin-patterns`
- `oc-symfony-dependency-injection`

These should only load when capabilities detect relevant files/config.

---

## 10. Harness Registry

### 10.1 Objetivo

Cada workflow activa harnesses. Los harnesses son componentes reutilizables, no fases hardcodeadas.

### 10.2 HarnessDefinition

```python
class HarnessDefinition(BaseModel):
    schema_version: str = "opencontext.harness.v1"
    id: str
    label: str
    type: Literal["context", "protocol", "mutation", "inspection", "diagnosis", "review", "escalation", "consolidation"]
    default_mode: Literal["off", "warn", "strict"]
    required_capabilities: list[str] = []
    inputs: list[str] = []
    outputs: list[str] = []
    gates: list[str] = []
    cost: Literal["zero_token", "low", "medium", "high"]
```

### 10.3 Harnesses obligatorios

#### Context Harness

Responsable:

- KG lookup;
- context pack;
- L1/L2/L3;
- omissions;
- token budget;
- owner metadata.

Debe reducir tokens por defecto.

#### Protocol Harness

Responsable:

- XML/Markdown/JSON parsing;
- output schema validation;
- no freeform when strict;
- rationale not chain-of-thought;
- convert mutation output to `ApplyEdit`.

#### Planning Harness

Responsable:

- no code in planning;
- task contract;
- acceptance criteria;
- design constraints.

#### Mutation Harness

Responsable:

- path containment;
- forbidden paths;
- `ApplyEdit`;
- checkpoint;
- rollback;
- patch;
- receipts.

#### Local Inspection Harness

Responsable:

- syntax;
- AST SRP;
- AST DIP;
- secrets;
- lint;
- tests;
- quality.

#### Diagnosis Harness

Responsable:

- reproduce;
- hypotheses;
- instrumentation;
- fix attempts;
- semantic GC;
- escalation.

#### Review Harness

Responsable:

- independent context;
- grounded findings;
- no praise/no fluff;
- severity;
- code economy.

#### Security Harness

Responsable:

- secrets;
- provider export;
- shell command risk;
- path escape;
- network calls.

#### Escalation Harness

Responsable:

- code owners;
- handoff report;
- pause;
- no more token burn.

#### Consolidation Harness

Responsable:

- KG reindex;
- memory harvest;
- summary;
- cleanup L1.

---

## 11. Harness matrix por workflow

### 11.1 SDD

| Harness | Default |
|---|---|
| Context | strict |
| Protocol | warn |
| Planning | strict |
| Mutation | strict |
| Inspection | warn |
| Diagnosis | off/optional |
| Review | strict |
| Security | warn |
| Escalation | warn |
| Consolidation | strict |

### 11.2 OC Flow

| Harness | Default |
|---|---|
| Context | strict |
| Protocol | strict |
| Planning | strict-lite |
| Mutation | strict |
| Inspection | strict |
| Diagnosis | strict |
| Review | optional |
| Security | warn/strict if sensitive |
| Escalation | strict |
| Consolidation | strict |

---

## 12. Context strategy for low tokens

### 12.1 Default: surgical-first

The default must never be “read everything”.

Flow:

```text
task
  -> extract candidate symbols
  -> opencontext_search
  -> KG node metadata
  -> callers/callees if needed
  -> impact if risky
  -> context pack only if still insufficient
```

### 12.2 Context layers

#### L3

Knowledge Graph master:

- signatures;
- spans;
- relationships;
- owners;
- test references;
- impact;
- architecture health.

No full code unless requested.

#### L2

Task contract:

- scope;
- acceptance;
- constraints;
- affected files;
- tests;
- owners;
- gates.

Immutable.

#### L1

Ephemeral:

- current file snippet;
- immediate error;
- latest stack trace;
- current hypothesis;
- current mutation.

Purge on success.

### 12.3 Token budget targets

| Workflow | Default max context | Target |
|---|---:|---|
| OC Flow | 3500-6500 | bugfix under 7k total |
| SDD quick | 6000-10000 | small feature under 15k |
| SDD full | 12000-25000 | formal change |
| Review | 4000-8000 | diff focused |

---

## 13. Mutation protocol

### 13.1 ApplyEdit first

`ApplyEdit` is primary.

```python
class ApplyEdit(BaseModel):
    path: str
    operation: Literal["replace_range", "insert_after", "delete_range", "create_file"]
    start_line: int | None = None
    end_line: int | None = None
    after_line: int | None = None
    content: str = ""
    reason: str
    requirement_refs: list[str] = []
    task_refs: list[str] = []
    checksum_before: str | None = None
    risk: Literal["low", "medium", "high"] = "low"
```

### 13.2 Whole-file fallback

Allowed only if:

- new file;
- generated file;
- massive restructure;
- config allows;
- reason recorded.

```yaml
mutation:
  whole_file_fallback: ask # deny|ask|allow
```

### 13.3 Receipts

Every mutation writes:

```json
{
  "path": "...",
  "operation": "replace_range",
  "changed": true,
  "checksum_before": "...",
  "checksum_after": "...",
  "reason": "...",
  "requirement_refs": ["REQ-1"],
  "diff_path": "patch-001.diff"
}
```

---

## 14. Inspection local-first

### 14.1 Required order

```text
protocol parse
mutation validation
path policy
syntax
AST SRP
AST DIP
secrets
lint
targeted tests
quality
broad tests
```

### 14.2 AST SRP

Default in balanced:

```yaml
srp:
  mode: warn
  max_useful_lines: 30
  max_complexity: 12
```

Enterprise:

```yaml
srp:
  mode: strict
  max_useful_lines: 25
  max_complexity: 10
```

### 14.3 AST DIP

Default in balanced:

```yaml
dip:
  mode: warn
```

Strict only when confident about project architecture.

### 14.4 First-run behavior

If no linter/test runner found:

- do not fail mysteriously;
- mark as blocked/skipped with reason;
- suggest exact config.

Example:

```text
Tests: skipped
Reason: no pytest, no unittest discovery, no package script found.
Suggestion: set inspection.tests.command in opencontext.yaml.
```

---

## 15. Diagnosis loop

### 15.1 OC Flow default

OC Flow diagnoses by default.

```yaml
diagnostics:
  enabled: true
  max_attempts: 2
  max_attempts_enterprise: 3
  hypothesis_count: 3
  semantic_gc_after_failures: 2
```

For first-run, use `2` attempts to control token burn. Enterprise can use `3`.

### 15.2 Method

```text
REPRODUCE
  -> HYPOTHESIZE exactly 3
  -> SELECT with evidence
  -> INSTRUMENT if needed
  -> FIX
  -> RECHECK
```

### 15.3 Stop conditions

Stop immediately if:

- protocol invalid after repair;
- forbidden path;
- security high risk;
- no owner/context and high blast radius;
- same strategy repeated;
- attempts exhausted.

---

## 16. SDD correction plan

### 16.1 Must fix now

1. Register `propose` in executor phases.
2. Propagate `envelope` in delegation results.
3. Add scaffold policy.
4. Persist handoffs between phases.
5. Make `ApplyEdit` primary.
6. Produce patch/receipts.
7. Upgrade verify local-first.
8. Add artifact carry-over for resume.
9. Improve `opencontext_run` summary.
10. Add workflow registry entry for SDD.

### 16.2 SDD first-run defaults

If user chooses SDD with no provider but host sampling available:

- use host sampling;
- no fake success;
- if scaffold appears, final status warning;
- show clear message.

If no host sampling:

```text
SDD planned mode completed with warning.
No model was available for generative phases.
Artifacts are scaffolds, not implementation-ready.
```

### 16.3 SDD should not overuse diagnosis

By default:

```yaml
sdd:
  diagnosis:
    enabled: false
```

But:

```yaml
sdd:
  diagnosis:
    enabled: true
    max_attempts: 1
```

can be used in enterprise/advanced.

---

## 17. OC Flow implementation plan

### 17.1 OC Flow MVP

Nodes:

- init
- gather_context
- plan
- mutate
- local_inspection
- consolidation

No diagnosis in MVP? For Gentle-like first-run, diagnosis must be in MVP. So MVP includes:

- diagnose
- escalation

### 17.2 OC Flow default prompt strategy

OC Flow should not ask the model to do everything.

Per node:

- gather_context: mostly KG, low/no LLM.
- plan: one small LLM call.
- mutate: one focused LLM call.
- inspection: zero LLM.
- diagnose: LLM only on failure.
- consolidation: mostly zero LLM, optional summarization.

### 17.3 OC Flow outputs

```text
l3-signatures.json
task-contract.json
mutation.xml
apply-receipts.json
patch.diff
inspection-report.json
diagnosis-attempts.json
run-summary.md
```

---

## 18. Capability Registry

### 18.1 Capabilities to probe

```text
kg_index_available
host_sampling_available
git_available
git_clean
python_project
pytest_available
ruff_available
mypy_available
node_project
npm_available
eslint_available
typescript_available
php_project
composer_available
phpunit_available
phpstan_available
phpcs_available
drupal_project
docker_available
opentelemetry_available
codeowners_available
```

### 18.2 First-run doctor

`opencontext init` should run:

```bash
opencontext doctor
```

Output:

```text
Detected:
✓ Git repository
✓ Python project
✓ pytest
✓ Knowledge graph index missing

Recommended:
run opencontext index

Workflow defaults:
auto -> oc-flow for bugfixes, sdd for features
```

### 18.3 Adaptive behavior

No pytest? Try:

- `python -m pytest`;
- `python -m unittest`;
- package scripts;
- skip with suggestion.

No KG? Use lexical fallback but warn:

```text
KG missing. Running with lexical context fallback. Token usage may increase.
```

---

## 19. Policy Engine

### 19.1 Presets

```yaml
permissive
balanced
restricted
air_gapped
```

### 19.2 Default balanced

```yaml
file_write: ask_if_high_risk
network: deny
secrets: redact
terminal: allow_safe
auto_apply: allow_low_risk
forbidden_paths:
  - .env
  - secrets/
  - private/
  - vendor/
  - node_modules/
```

### 19.3 Integration

Every harness operation asks policy:

```python
decision = policy.evaluate(operation, context)
```

No direct file write without policy.

---

## 20. UX Configuration

### 20.1 Single config file

```yaml
version: 2
profile: balanced

workflow:
  default: auto
  first_run: oc-flow
  available:
    - sdd
    - oc-flow

runtime:
  mode: run_to_completion
  session_store: local
  resume: true
  checkpoints: true
  live_state: true

context:
  strategy: surgical_first
  l1:
    enabled: true
    max_tokens: 1500
    purge_on_success: true
  l2:
    enabled: true
    immutable: true
    max_tokens: 2500
  l3:
    enabled: true
    mode: signatures
    max_symbols: 50
    include_owners: true

personas:
  registry: builtin
  allow_project_overrides: true
  defaults:
    orchestrator: oc-orchestrator
    explorer: oc-explorer
    context_engineer: oc-context-engineer
    architect: oc-architect
    builder: oc-builder
    diagnostician: oc-diagnostician
    verifier: oc-harness-verifier
    reviewer: oc-reviewer
    archivist: oc-archivist

skills:
  registry:
    builtin: true
    project: true
    user: true
  bundles:
    sdd: sdd_default
    oc-flow: oc_flow_default
  max_skills_per_node: 3
  max_rules_per_skill: 6
  enforce_contracts: true

harnesses:
  context: strict
  protocol: workflow_default
  mutation: strict
  inspection: strict
  diagnosis: workflow_default
  review: workflow_default
  security: warn
  escalation: strict
  consolidation: strict

inspection:
  local_first: true
  syntax: true
  secrets: true
  lint: auto
  tests: targeted
  ast:
    srp:
      mode: warn
      max_useful_lines: 30
      max_complexity: 12
    dip:
      mode: warn

diagnostics:
  enabled: true
  max_attempts: 2
  hypothesis_count: 3
  semantic_gc_after_failures: 2
  prevent_repeated_strategy: true

memory:
  enabled: true
  provider: local
  project_memory: true
  episodic: true
  failure_patterns: true
  semantic_gc: true

policies:
  preset: balanced
  auto_apply: ask_if_risky
  network: deny_by_default
  secrets: redact

observability:
  events: jsonl
  live_state: true
  dashboard: true
  opentelemetry:
    enabled: false
```

### 20.2 Profiles

#### balanced

Default.

Goal:

- good first run;
- controlled tokens;
- local-first;
- 2 diagnosis attempts.

#### low-cost

- OC Flow default;
- max 1 diagnosis attempt;
- smaller context;
- no broad context unless user asks.

#### enterprise

- SDD for high-risk;
- stricter gates;
- approval required for writes;
- OpenTelemetry enabled;
- 3 attempts.

#### research

- SDD default;
- more context;
- artifacts prioritized.

#### performance

- local-first;
- minimal LLM;
- aggressive cache/context reuse.

---

## 21. MCP API

### 21.1 Keep existing

`opencontext_run` remains.

### 21.2 Extend `opencontext_run`

Input:

```json
{
  "task": "...",
  "workflow": "auto|sdd|oc-flow|quick|standard",
  "profile": "balanced",
  "mode": "run_to_completion|interactive",
  "root": "..."
}
```

Output:

```json
{
  "session_id": "...",
  "run_id": "...",
  "workflow": "oc-flow",
  "workflow_selection": {
    "selected": "oc-flow",
    "reason": "...",
    "confidence": 0.86
  },
  "status": "completed",
  "summary": "...",
  "token_usage": {
    "estimated": 5200,
    "saved_by_surgical_context": 11000
  },
  "artifacts": {
    "patch": "...",
    "receipts": "...",
    "inspection": "...",
    "summary": "..."
  },
  "gates": {
    "passed": 9,
    "warning": 1,
    "failed": 0
  },
  "next_recommended": "Review patch.diff"
}
```

### 21.3 New tools

```text
opencontext_workflow_list
opencontext_workflow_explain
opencontext_profile_list
opencontext_profile_explain
opencontext_session_start
opencontext_session_next
opencontext_session_observe
opencontext_session_apply
opencontext_session_inspect
opencontext_session_status
opencontext_session_resume
opencontext_session_archive
opencontext_doctor
```

---

## 22. CLI UX

### 22.1 First install

```bash
opencontext init
```

Should ask at most:

```text
Choose default profile:
1. Balanced (recommended)
2. Low cost
3. Enterprise
4. Research
```

Then:

```text
Detected Python project with pytest.
Default workflow: auto.
For bugfixes I will use OC Flow.
For features I will use SDD.
Run `opencontext index` next.
```

### 22.2 Run

```bash
opencontext run "Fix failing test"
```

Default:

- workflow auto;
- profile balanced;
- run to completion;
- interactive only if approval needed.

### 22.3 Explainability

```bash
opencontext workflow explain oc-flow
opencontext why <session_id>
```

`why` should explain:

- why workflow selected;
- why context selected;
- why gate failed;
- why escalation happened.

---

## 23. Telemetry and Dashboard

### 23.1 Required files

```text
.opencontext/sessions/<session_id>/
  session.json
  live-state.json
  events.jsonl
  summary.json
  config-snapshot.yaml
```

### 23.2 Live state example

```json
{
  "workflow": "oc-flow",
  "node": "diagnose",
  "status": "running",
  "message": "Hypothesis 2/3 selected; preparing surgical fix",
  "attempt": 1,
  "max_attempts": 2
}
```

### 23.3 Dashboard should show

- workflow;
- current node;
- persona;
- active skill bundle;
- token budget;
- gates;
- artifacts;
- diagnosis attempts;
- next action.

---

## 24. Memory strategy

### 24.1 What to save

Save:

- durable decisions;
- project conventions;
- confirmed failure patterns;
- test/lint environment quirks;
- code owner mappings;
- successful procedural patterns.

Do not save:

- chain-of-thought;
- raw long logs;
- full source files;
- bad code attempts;
- prompts.

### 24.2 Project memory files

```text
.opencontext/memory/
  decisions.md
  conventions.md
  failure-patterns.md
  environment.md
  code-owners.json
```

### 24.3 Runtime memory records

Use existing memory store with:

- `run_id`;
- `provenance`;
- layer;
- confidence;
- tags.

---

## 25. Roadmap by PRs

### PR 0 — Golden first-run tests

Before implementation, define acceptance tests.

Tests:

- first install balanced config;
- workflow auto selects OC Flow for bugfix;
- workflow auto selects SDD for feature;
- no KG fallback message;
- no model produces planned warning;
- with host sampling produces real artifact;
- oc-flow bugfix produces patch + inspection.

### PR 1 — Workflow Registry

Deliver:

- `WorkflowDefinition`;
- `WorkflowRegistry`;
- `sdd.yaml`;
- `oc-flow.yaml`;
- alias support.

### PR 2 — Runtime Session

Deliver:

- `RuntimeSession`;
- `SessionStore`;
- `events.jsonl`;
- `live-state.json`.

### PR 3 — Event Bus and improved summaries

Deliver:

- `RuntimeEvent`;
- event bus;
- improved `opencontext_run` output.

### PR 4 — Persona Registry

Deliver:

- move personas to registry model;
- keep existing Python definitions compatible;
- add `oc-diagnostician`;
- add `oc-security-reviewer`.

### PR 5 — Skill Registry v2

Deliver:

- `SkillDefinition`;
- skill bundles;
- contract enforcement;
- builtins:
  - context-surgical;
  - apply-surgical;
  - inspect-local-first;
  - diagnose-three-hypotheses;
  - semantic-gc;
  - escalation-owner.

### PR 6 — Harness Registry

Deliver:

- harness definitions;
- harness matrix per workflow;
- config integration.

### PR 7 — SDD hardening

Deliver:

- `propose` executor;
- delegation envelope propagation;
- scaffold policy;
- phase handoffs;
- artifact carry-over resume.

### PR 8 — Apply receipts and patch

Deliver:

- primary ApplyEdit;
- checksums;
- receipts;
- patch.diff;
- rollback report.

### PR 9 — OC Flow MVP

Deliver:

- init;
- gather_context;
- plan;
- mutate;
- local_inspection;
- diagnose;
- escalation;
- consolidation.

### PR 10 — Protocol Harness

Deliver:

- XML parser;
- rationale, not thought;
- mutation conversion;
- protocol violation handling.

### PR 11 — Local Inspection Harness

Deliver:

- syntax;
- SRP;
- DIP;
- secrets;
- lint/test adapters;
- capability-aware skip/block.

### PR 12 — Diagnosis Harness

Deliver:

- reproduce;
- exactly 3 hypotheses;
- instrument;
- fix;
- semantic GC;
- anti-repeat strategy.

### PR 13 — Capability Registry + doctor

Deliver:

- project probes;
- `opencontext doctor`;
- workflow auto selector inputs.

### PR 14 — Policy Engine

Deliver:

- policy presets;
- file/command/network/provider decisions;
- integration with mutation/apply.

### PR 15 — UX Profiles

Deliver:

- balanced;
- low-cost;
- enterprise;
- research;
- performance;
- config wizard.

### PR 16 — Dashboard/TUI

Deliver:

- live-state view;
- workflow timeline;
- artifacts;
- gates;
- diagnosis status.

### PR 17 — Docs + migration

Deliver:

- SDD docs;
- OC Flow docs;
- first-run guide;
- config guide;
- troubleshooting.

---

## 26. Definition of Done final

This iteration is done only if:

### First-run

- `opencontext init --profile balanced` creates usable config.
- `opencontext doctor` explains capabilities.
- `opencontext run "fix failing test"` works with `workflow=auto`.
- User receives patch/summary/artifacts, not raw internal noise.

### SDD

- SDD still works.
- SDD has proper harnesses.
- SDD personas are used by contract.
- SDD scaffolds never masquerade as success.
- SDD phase handoffs are persisted.
- SDD apply produces receipts and patch.
- SDD verify is local-first.
- SDD resume carries artifacts.

### OC Flow

- OC Flow exists as independent workflow.
- OC Flow uses context layers.
- OC Flow uses personas/skills/harnesses.
- OC Flow diagnoses failures.
- OC Flow escalates after bounded attempts.

### Personas

- Personas are registry-driven.
- Existing personas preserved.
- Missing personas added.
- Tool permissions are workflow/node aware.
- Output contracts enforced.

### Skills

- Skills are contract-driven.
- Bundles exist for SDD and OC Flow.
- Builtin core skills exist.
- Language/framework skills load by capability.
- Skills can define gates.

### Harnesses

- Harness registry exists.
- Context, protocol, mutation, inspection, diagnosis, review, security, escalation, consolidation harnesses exist.
- Each workflow activates harnesses declaratively.

### Tokens

- Default context is surgical-first.
- Broad context requires evidence/config.
- First bugfix target stays under controlled token budget.
- Semantic GC runs after repeated failures.

### UX

- Profiles exist.
- Workflow explanations exist.
- Config is centralized.
- MCP output is useful.
- CLI output is useful.
- TUI/dashboard can show live progress.

---

## 27. Final architecture statement

The final product should feel like this:

```text
OpenContext knows my codebase.
OpenContext chooses the right workflow.
OpenContext uses the right personas.
OpenContext loads only the skills needed.
OpenContext edits surgically.
OpenContext verifies locally before spending tokens.
OpenContext diagnoses methodically.
OpenContext stops when it should stop.
OpenContext explains what happened.
```

That is the target.

Not just a phase runner.

Not just an MCP server.

Not just a context pack generator.

A deterministic, observable, configurable agentic engineering runtime where SDD and OC Flow coexist, share optimized harnesses, and deliver a useful first task with low token usage.
