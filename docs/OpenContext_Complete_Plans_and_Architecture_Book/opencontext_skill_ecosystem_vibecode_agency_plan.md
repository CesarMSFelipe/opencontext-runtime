# OpenContext Skill Ecosystem v2 — Plan complementario inspirado en `agency-agents` y `vibecode-pro-max-kit`

**Documento complementario al blueprint principal:** `OpenContext Agentic Runtime v4 — SDD + OC Flow con calidad tipo Gentle AI`  
**Repos revisados como inspiración:**  
- `msitarzewski/agency-agents`  
- `withkynam/vibecode-pro-max-kit`  
- patrones del ecosistema `SKILL.md`, agentes especializados, protocolos, validadores y autopilot loops.

> Este documento no propone copiar repos externos ni depender de ellos. Propone absorber sus mejores patrones, normalizarlos al modelo de OpenContext y convertirlos en un ecosistema propio de skills, agentes/personas, harnesses y validadores verificables.

---

## 0. Resumen ejecutivo

El plan principal definía cómo OpenContext debe funcionar como runtime agentic con dos workflows principales:

```text
SDD     -> workflow formal, spec-driven, con fases/harnesses robustos.
OC Flow -> workflow operativo, rápido, local-first, diagnóstico y con bajo consumo de tokens.
```

Este documento añade la capa que faltaba para que la experiencia sea realmente “Gentle-like” en la primera instalación:

```text
Skill Ecosystem
  -> builtin skills
  -> skill bundles por workflow
  -> skill tiers
  -> context/plan discovery
  -> project setup
  -> audit validators
  -> update/publish lifecycle
  -> autoresearch loops
  -> multi-tool compatibility
  -> machine-readable skill catalog
  -> quality scoring
  -> skill governance
```

La idea principal:

> OpenContext no debe limitarse a “tener skills”. Debe tener un **sistema operativo de skills**: detectables, versionadas, auditables, validadas, con contratos, gates, bundles, métricas y lifecycle.

---

## 1. Qué aporta `vibecode-pro-max-kit`

`vibecode-pro-max-kit` es especialmente relevante porque no es solo una colección de prompts. Es un kit de proceso con:

- instalación en un comando;
- setup interactivo;
- detección de stack;
- contexto persistente;
- RIPER-5 plan-first workflow;
- autopilot;
- self-healing loops;
- strategy picker;
- model-cost strategy;
- intent clarification;
- validators;
- phase programs;
- project memory;
- quick/fast/full lanes;
- layered skills;
- agentes especializados;
- hooks;
- update/publish lifecycle.

Elementos especialmente aprovechables para OpenContext:

| Patrón | Valor para OpenContext |
|---|---|
| One-command setup | Primera experiencia usable |
| Bootstrap guard | No permitir tareas si contexto base falta |
| Skill tiers | Saber qué skills son obligatorias vs condicionales |
| Context router | Evitar leer todo; cargar solo lo necesario |
| Skill catalog generado | Routing y auditoría mecánica |
| Audit validators | Evitar drift en skills/context/protocols |
| Dry-run update | Lifecycle seguro de harnesses |
| Publish process | Mantener core/builtin skills sin fugas de proyecto |
| PVL/EVL loops | Reparación y convergencia controlada |
| Strategy picker | Elegir agente único, paralelo o team con coste |
| Plan lifecycle | Artifact management durable |
| Subagent status protocol | DONE/BLOCKED/NEEDS_CONTEXT usable por runtime |
| Quick/Fast/Full lanes | UX por riesgo/coste |
| Multi-tool compatibility | Claude/Codex/OpenCode/Cursor/Windsurf/etc. |

---

## 2. Qué aporta `agency-agents`

`agency-agents` aporta otro tipo de valor: una biblioteca amplia de especialistas, cada uno con:

- identidad clara;
- dominio específico;
- entregables;
- criterios de éxito;
- estilo de comunicación;
- install/conversion para múltiples tools;
- selección por división/equipo.

OpenContext no necesita 100+ agentes de negocio/marketing, pero sí debe importar el patrón:

```text
specialized agents/personas
  -> clear specialty
  -> when to use
  -> deliverables
  -> success metrics
  -> communication contract
  -> installable subsets
```

De `agency-agents`, los perfiles más útiles para OpenContext serían:

- Frontend Developer
- Backend Architect
- AI Engineer
- DevOps Automator
- Senior Developer
- Incident Response Commander
- Codebase Onboarding Engineer
- Technical Writer
- Code Reviewer
- Database Optimizer
- Git Workflow Master
- Software Architect
- SRE
- Data Engineer
- CMS Developer
- Minimal Change Engineer
- Prompt Engineer
- Multi-Agent Systems Architect
- Drupal Shopping Cart Engineer
- CMS/Drupal/WordPress Engineering specialists

No se añaden como agentes “decorativos”, sino como **persona extensions** activables por capability y workflow.

---

## 3. Principio de integración

OpenContext ya tiene tres capas que deben seguir siendo el núcleo:

```text
Knowledge Graph
Context-as-Code
Harness/Runtime
```

Por tanto, todas las skills importadas o inspiradas externamente deben convertirse a este formato:

```yaml
schema_version: opencontext.skill.v1
id: oc-...
source_inspiration:
  - vibecode-pro-max-kit: ...
  - agency-agents: ...
workflows:
  - sdd
  - oc-flow
personas:
  - ...
tier: 0|1|2
mode:
  - simple
  - deep
required_capabilities:
  - ...
inputs:
  - ...
outputs:
  - ...
gates:
  - ...
token_budget:
  simple: ...
  deep: ...
failure_policy:
  - ...
```

La skill no es un prompt. Es un **contrato operativo verificable**.

---

## 4. Nueva arquitectura del ecosistema de skills

```text
opencontext_core/
  skills/
    registry.py
    resolver.py
    contracts.py
    catalog.py
    validator.py
    scoring.py
    bundles.py
    tiers.py
    lifecycle.py
    importers/
      claude_skill.py
      codex_agent.py
      markdown_agent.py
      agency_agent.py
      vibecode_skill.py
    builtins/
      core/
      context/
      planning/
      mutation/
      inspection/
      diagnosis/
      review/
      security/
      release/
      docs/
      language/
      framework/
    scripts/
      validate_skill_contracts.py
      generate_skill_catalog.py
      audit_skill_routing.py
      audit_skill_dependencies.py
      audit_confusable_skills.py
      benchmark_skills.py
```

---

## 5. Skill tiers

Adoptar el patrón de tiers, pero adaptado a OpenContext.

### 5.1 Tier 0 — Siempre al entrar en un workflow/node

Estas skills se ejecutan en forma abreviada por defecto para controlar tokens.

| Skill | Propósito |
|---|---|
| `oc-intent-clarify` | Restate scope, detect ambiguity, ask only if needed |
| `oc-context-discovery` | Identify required context using KG/context routers |
| `oc-plan-discovery` | Check existing active plans/sessions/artifacts before duplicating |
| `oc-review-situation` | Check git branch, dirty worktree, active session |
| `oc-strategy-compare` | Choose single agent vs sequential vs parallel/team, with cost |

### 5.2 Tier 1 — Obligatorio por fase/nodo

| Skill | SDD | OC Flow |
|---|---|---|
| `oc-scout` | explore/design/apply | gather_context |
| `oc-requirements-rfc2119` | spec | optional |
| `oc-generate-spec` | spec | optional |
| `oc-design-minimal` | design | plan |
| `oc-task-splitting` | tasks | optional |
| `oc-validate-contract` | before apply/execute | plan/mutate |
| `oc-apply-surgical` | apply | mutate |
| `oc-inspect-local-first` | verify | local_inspection |
| `oc-autoresearch` | optional PVL/EVL | diagnose |
| `oc-archive-memory` | archive | consolidation |

### 5.3 Tier 2 — Condicional

| Skill | Se activa cuando |
|---|---|
| `oc-security-review` | auth, secrets, billing, public API, trust boundary |
| `oc-risk-evidence-pack` | high-risk change |
| `oc-web-testing` | browser/UI/frontend affected |
| `oc-db-migration-safety` | schema/migration/db affected |
| `oc-performance-review` | hot path, query, loop, cache |
| `oc-docs-update` | public API or docs changed |
| `oc-release-check` | versioning/package/release |
| `oc-drupal-patterns` | Drupal project detected |
| `oc-phpstan-phpcs` | PHP project detected |
| `oc-agent-strategy-compare-deep` | parallelizable or ambiguous work |
| `oc-context-audit` | context files changed |
| `oc-skill-audit` | skill/persona/harness files changed |

---

## 6. Simple vs Deep mode

Importar el patrón de simple/deep mode.

### 6.1 Simple mode

Default.

Usa:

- contexto ya disponible;
- KG signatures;
- L1/L2/L3;
- sin subagent adicional;
- sin broad context salvo necesidad.

### 6.2 Deep mode

Solo cuando un trigger lo justifica:

- blast radius amplio;
- auth/security/schema;
- 3+ paquetes;
- arquitectura;
- fallo tras varios intentos;
- información contradictoria;
- plan de muchas fases.

### 6.3 Contrato

Cada skill que soporte ambos modos debe declarar:

```yaml
modes:
  simple:
    token_budget: 500
    max_files: 3
  deep:
    token_budget: 3000
    requires_approval_if_cost_high: true
```

El runtime debe registrar:

```json
{
  "skill": "oc-risk-evidence-pack",
  "mode": "deep",
  "reason": "Auth boundary touched and 4 packages affected"
}
```

---

## 7. Intent clarification

Tomar el patrón de `vc-intent-clarify`.

### 7.1 Objetivo

Evitar que el agente haga la tarea incorrecta.

### 7.2 Skill: `oc-intent-clarify`

Input:

```json
{
  "task": "...",
  "workflow": "auto",
  "context_available": true
}
```

Output:

```json
{
  "ambiguity_score": 0,
  "restated_intent": "...",
  "questions": [],
  "auto_proceed": true
}
```

### 7.3 Reglas

| Score | Acción |
|---:|---|
| 0-1 | auto-proceed with one-line restatement |
| 2 | inline assumption summary |
| 3+ | ask focused multiple-choice question |
| 4 | stop until clarified |

Para `opencontext_run --mode autopilot`, score 0-2 auto-proceed; score 3+ pauses.

---

## 8. Context discovery y context router

### 8.1 Inspiración

`vibecode` usa `process/context/all-context.md` como router y exige seguir rutas profundas. OpenContext debe mapear esto a:

```text
KG + Context-as-Code + generated context catalog
```

### 8.2 Skill: `oc-context-discovery`

Responsabilidades:

- detectar project context;
- localizar context routers;
- leer solo entrypoints relevantes;
- seguir rutas profundas si router lo exige;
- consultar KG;
- producir `ContextEnvelope`.

### 8.3 ContextEnvelope

```python
class ContextEnvelope(BaseModel):
    schema_version: str = "opencontext.context_envelope.v1"
    session_id: str
    workflow: str
    node: str
    task: str
    included_files: list[str]
    included_symbols: list[str]
    included_context_docs: list[str]
    omitted_with_reason: list[dict[str, str]]
    active_plan_refs: list[str]
    risk_flags: list[str]
    token_estimate: int
```

### 8.4 Audit

Añadir `oc-audit-context` como equivalente OpenContext de `vc-audit-context`.

Debe validar:

- context router existe;
- context groups no están huérfanos;
- docs >800 LOC se recomiendan para split;
- skill routing catalog está actualizado;
- no hay links rotos;
- context docs con frontmatter válido;
- KG refs resolvibles;
- no hay context drift tras cambios.

---

## 9. Plan discovery y plan lifecycle

### 9.1 Inspiración

`vibecode` tiene surfaces de planes:

```text
process/general-plans/active/
process/features/{feature}/active/
```

OpenContext ya tiene runs/artifacts, pero necesita un equivalente durable para planes y sesiones.

### 9.2 OpenContext plan surfaces

```text
.opencontext/plans/general/active/
.opencontext/plans/general/completed/
.opencontext/plans/features/{feature}/active/
.opencontext/plans/features/{feature}/completed/
.opencontext/plans/backlog/
```

Alternativa para repos que prefieran visible docs:

```text
process/opencontext/plans/...
```

Config:

```yaml
plans:
  storage: ".opencontext/plans"
  visible_process_dir: false
```

### 9.3 Skill: `oc-plan-discovery`

Antes de crear un plan:

- buscar active sessions;
- buscar active plans;
- buscar completed related plans;
- detectar overlap;
- proponer resume vs new plan.

### 9.4 Plan frontmatter

```yaml
---
name: plan:{slug}
description: "{summary}"
date: "2026-06-27"
metadata:
  node_type: memory
  type: plan
  workflow: sdd|oc-flow
  status: active
---
```

### 9.5 Resume rule

No crear un plan nuevo si hay un active plan coincidente, salvo aprobación del usuario.

---

## 10. Review situation

### 10.1 Skill: `oc-review-situation`

Inspirada en `vc-review-situation`.

Debe comprobar:

- git branch;
- dirty worktree;
- untracked files;
- active session;
- active plan;
- incomplete previous run;
- config validity;
- KG index freshness;
- capability availability.

Output:

```json
{
  "branch": "feat/agentic-engineering-runtime",
  "dirty": true,
  "active_sessions": [],
  "active_plans": [],
  "kg_fresh": true,
  "warnings": [
    "Worktree has uncommitted changes"
  ],
  "allowed_to_continue": true
}
```

---

## 11. Strategy compare

### 11.1 Inspiración

`vibecode` compara one agent vs many vs coordinated team con coste.

OpenContext debe añadir `oc-strategy-compare`.

### 11.2 Estrategias

```text
single-agent
sequential-personas
parallel-readers
agent-team
local-only
```

### 11.3 Señales

1. Número de archivos.
2. Blast radius.
3. Independencia de subproblemas.
4. Riesgo de integración.
5. Necesidad de investigación.
6. Coste estimado de tokens.
7. Disponibilidad de herramientas locales.

### 11.4 Resultado

```json
{
  "selected": "sequential-personas",
  "reason": "Requires architect then builder; no independent parallel scopes",
  "estimated_tokens": 5500,
  "alternatives": [
    {
      "strategy": "agent-team",
      "cost": "high",
      "reason_rejected": "Scopes not independent enough"
    }
  ]
}
```

### 11.5 Integración con SDD/OC Flow

SDD:

- default sequential-personas;
- agent-team only for phase programs or large research.

OC Flow:

- default single/sequential;
- parallel-readers only when context discovery sees 7+ relevant files.

---

## 12. Subagent status protocol

### 12.1 Adoptar estados canónicos

```text
DONE
DONE_WITH_CONCERNS
BLOCKED
NEEDS_CONTEXT
```

OpenContext debe mapearlos a envelopes.

```python
class SubAgentStatus(StrEnum):
    DONE = "done"
    DONE_WITH_CONCERNS = "done_with_concerns"
    BLOCKED = "blocked"
    NEEDS_CONTEXT = "needs_context"
```

### 12.2 Reglas

- Nunca ignorar `BLOCKED`.
- Nunca ignorar `NEEDS_CONTEXT`.
- `DONE_WITH_CONCERNS` puede avanzar solo si concerns no bloquean gates.
- `BLOCKED` va a diagnose/escalation.
- `NEEDS_CONTEXT` vuelve a context discovery.

### 12.3 Footer obligatorio

Para agentes humanos/markdown:

```md
**Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
**Summary:** ...
**Concerns/Blockers:** ...
```

Para runtime:

```json
{
  "status": "blocked",
  "summary": "...",
  "concerns": [],
  "blockers": []
}
```

---

## 13. Autopilot / goal block

### 13.1 Inspiración

`vibecode` tiene `/goal` para que el agente siga fase tras fase y pueda resumir en sesión nueva.

OpenContext debe implementar `Session Goal Block`.

### 13.2 Archivo

```text
.opencontext/sessions/<session_id>/goal.md
```

### 13.3 Contenido

```yaml
---
schema_version: opencontext.goal.v1
session_id: ...
workflow: oc-flow
decision_policy: auto_low_risk_ask_high_risk
max_iterations: 2
created_at: ...
---
```

```md
# Goal

Fix failing session resume test.

## Decision Policy

- Auto-apply low-risk surgical edits.
- Ask before public API, auth, secrets, broad refactor.
- Stop after 2 failed diagnosis attempts.

## Current State

- Workflow: oc-flow
- Node: diagnose
- Attempt: 1/2
- Last gate: tests_failed

## Known Constraints

- Do not rewrite session store.
- Preserve existing artifact layout.
```

### 13.4 Usage

`opencontext run --goal "..."` creates a goal block.

`opencontext session resume <id>` reads it.

---

## 14. PVL / EVL loops

### 14.1 Importar como OpenContext primitive

`vc-autoresearch` is “find gaps → fix → repeat”. OpenContext should implement:

```text
oc-autoresearch
```

Domains:

```text
plan
tests
docs
context
skills
security
quality
```

### 14.2 PVL

Plan Validate Loop.

Used in SDD:

```text
plan/spec/design/tasks validation
```

Used in OC Flow:

```text
plan-lite validation before mutate
```

### 14.3 EVL

Execute Validate Loop.

Used in OC Flow diagnosis:

```text
mutation -> inspection -> fix -> inspection
```

### 14.4 Termination

Priority:

```text
SUCCESS
PLATEAU
SEVERITY_ESCALATION
CAP
REGRESSION
```

### 14.5 Iteration report

```text
.opencontext/sessions/<session_id>/loops/
  oc-autoresearch-plan-001.json
  oc-autoresearch-tests-001.json
  results.tsv
```

### 14.6 Token control

Default max loops:

| Domain | Default |
|---|---:|
| plan | 2 |
| tests | 2 |
| docs | 2 |
| context | 1 |
| skills | 1 |
| enterprise tests | 3 |

The 10-cycle cap from vibecode is too high for OpenContext defaults. Keep high caps only for explicit `enterprise` or `full` mode.

---

## 15. Setup skill

### 15.1 Skill: `oc-setup`

Inspired by `vc-setup`.

### 15.2 Goals

First install should:

- detect stack;
- detect project type;
- detect existing config;
- ask minimal useful questions;
- scaffold OpenContext config;
- index project;
- generate context routers;
- validate setup.

### 15.3 Flow A — New project

```text
DETECT
  -> ASK
  -> SCAFFOLD
  -> STUDY
  -> VALIDATE
```

Questions should be adaptive, not a long fixed form.

Minimal first-run questions:

1. What is this project?
2. What kind of tasks do you want OpenContext to help with first?
3. Are there areas it must not touch automatically?
4. How do you run tests/lint/type checks?

If capability detection answers 4, do not ask it.

### 15.4 Flow B — Existing project

```text
STUDY_EXISTING
  -> PRESENT_FINDINGS
  -> ASK_APPROVAL
  -> MERGE_SCAFFOLD
  -> STUDY
  -> VALIDATE
```

Never silently reorganize user files.

### 15.5 Outputs

```text
opencontext.yaml
.opencontext/context/all-context.md
.opencontext/context/tests/all-tests.md
.opencontext/skills/generated-skills-catalog.json
.opencontext/project-profile.json
```

### 15.6 Bootstrap guard

Before substantial task:

```text
if no .opencontext/context/all-context.md and no KG index:
  run opencontext setup or index first
```

But UX:

- For tiny tasks, allow lexical fallback with warning.
- For SDD full, block and ask setup/index.

---

## 16. Update skill

### 16.1 Skill: `oc-update`

Inspired by `vc-update`.

### 16.2 Goals

Safely update builtin OpenContext skills/harnesses/personas.

### 16.3 Flow

```text
check worktree
read current version
fetch/update builtin pack
resolve manifest
compute dry-run diff
print summary
ask confirmation
apply changes
run validators
write snapshot
```

### 16.4 Dry-run summary

```text
oc-update dry run: v1.4.0 -> v1.5.0

SKILLS:
  [modified] oc-diagnose-three-hypotheses
  [new]      oc-db-migration-safety
  [removed]  oc-old-context-router

PERSONAS:
  [modified] oc-diagnostician

HARNESSES:
  [modified] inspection.local_first

MERGE:
  [preserved] project overrides

Summary: 3 modified, 1 new, 1 removed
```

### 16.5 Safety

- never overwrite project skills;
- never delete custom skills outside owned namespace;
- warn on large delete;
- keep `.opencontext-installed-files`.

---

## 17. Publish skill

### 17.1 Skill: `oc-publish-pack`

Inspired by `vc-publish`.

### 17.2 Use case

Maintainers publish OpenContext builtin skills/personas/harnesses.

### 17.3 Flow

```text
load publish config
read manifest
generate skill catalog
resolve pack file set
compute diff
print summary
confirm version bump
apply changes
run leak detection
run validators
commit/tag/release
```

### 17.4 Leak detection

Critical. Builtin packs must not contain project-specific data.

Scan for:

- absolute paths;
- project names;
- secrets;
- private repo names;
- local usernames;
- customer names;
- environment URLs.

---

## 18. Audit skills

### 18.1 Skill: `oc-audit-skills`

Inspired by `vc-audit-context` and `audit-vc`.

### 18.2 Validators

```text
validate-skill-frontmatter
validate-skill-contracts
validate-skill-routing
validate-skill-keywords
validate-skill-dependencies
validate-confusable-skills
generate-skill-catalog --check
validate-workflow-bundles
validate-persona-skill-compatibility
```

### 18.3 Generated catalog

```text
.opencontext/skills/generated-skills-catalog.json
```

Schema:

```json
{
  "generated_at": "...",
  "skills": [
    {
      "id": "oc-apply-surgical",
      "tier": 1,
      "workflows": ["sdd", "oc-flow"],
      "personas": ["oc-builder"],
      "triggers": ["apply", "mutate", "edit"],
      "gates": ["apply_receipt_created", "patch_created"]
    }
  ]
}
```

### 18.4 Drift detection

Audit fails/warns if:

- skill referenced by workflow bundle missing;
- persona requires missing skill;
- skill references missing gate;
- two skills have overlapping triggers with no priority;
- project override shadows builtin without version;
- skill has no token budget;
- skill has no output contract;
- skill has no clear “when not to use”.

---

## 19. Context audit

### 19.1 Skill: `oc-audit-context`

Should run when:

- context files change;
- KG index changes drastically;
- setup/update runs;
- SDD archive writes memory;
- OC Flow consolidation updates context.

### 19.2 Checks

- root router exists;
- all referenced files exist;
- no context file > threshold without split recommendation;
- stale file paths detected;
- context groups have entrypoints;
- plans and features indexed;
- generated catalog current;
- no orphan context docs.

---

## 20. Phase programs

### 20.1 Inspired by `vibecode` phase programs

For large work, do not run one giant SDD or OC Flow.

Use:

```text
Program
  -> umbrella plan
  -> phase plans
  -> phase-by-phase SDD/OC Flow runs
  -> inter-phase validation
```

### 20.2 OpenContext structure

```text
.opencontext/programs/<program_id>/
  umbrella-plan.md
  phase-01-plan.md
  phase-01-report.md
  phase-02-plan.md
  phase-02-report.md
  blast-radius-registry.md
  current-state.json
```

### 20.3 Skill: `oc-generate-phase-program`

Use when:

- 3+ dependent phases;
- multi-package;
- major refactor;
- migration;
- new product area;
- large user request.

### 20.4 Workflow

```text
research
  -> design phase split
  -> validate phase boundaries
  -> execute phase 1
  -> verify/regression
  -> update context
  -> move to phase 2
```

---

## 21. Quick / Fast / Full lanes

### 21.1 Lanes

| Lane | Use |
|---|---|
| quick | trivial fixes |
| fast | small task but needs verify |
| full | formal/high-risk work |

### 21.2 Mapping to OpenContext

```yaml
lanes:
  quick:
    workflow: oc-flow
    max_context_tokens: 2500
    diagnostics_attempts: 1
    review: false
  fast:
    workflow: oc-flow
    max_context_tokens: 6500
    diagnostics_attempts: 2
    review: optional
  full:
    workflow: sdd
    max_context_tokens: 20000
    diagnostics_attempts: 2
    review: true
```

### 21.3 Auto lane selection

Signals:

- changed files estimate;
- risk;
- task type;
- user urgency;
- test availability;
- KG confidence.

---

## 22. Multi-tool compatibility

### 22.1 Pattern from vibecode and agency-agents

Both support more than one agent tool surface. OpenContext should support:

- MCP-native;
- Claude Code;
- Codex;
- OpenCode;
- Cursor;
- Windsurf;
- Aider-like adapters;
- local CLI.

### 22.2 Adapter layer

```text
adapters/
  mcp/
  claude/
  codex/
  opencode/
  cursor/
```

### 22.3 Shared source of truth

OpenContext must avoid duplicating agent definitions manually.

Single source:

```text
opencontext_core/personas/builtins/*.yaml
opencontext_core/skills/builtins/*/SKILL.md
```

Generated surfaces:

```text
.claude/agents/
.codex/agents/
.agents/skills/
```

### 22.4 Validation

`oc-audit-adapters`:

- Claude/Codex parity;
- generated files in sync;
- no project content leaks;
- no stale wrappers.

---

## 23. Hooks

### 23.1 Inspiration

`vibecode` has hooks for session init and safety.

OpenContext should add hook points:

```text
session_init
pre_tool_use
post_tool_use
pre_apply
post_apply
pre_inspection
post_inspection
pre_archive
```

### 23.2 HookDefinition

```python
class HookDefinition(BaseModel):
    id: str
    event: str
    mode: Literal["advisory", "blocking"]
    command: str | None
    python_callable: str | None
    timeout_s: int
```

### 23.3 Builtin hooks

- `session_bootstrap_guard`
- `dirty_worktree_warning`
- `forbidden_path_guard`
- `secret_scan_pre_apply`
- `large_delete_warning`
- `skill_catalog_sync_check`
- `context_router_sync_check`

---

## 24. Best skills to add from the combined ecosystem

### 24.1 Core orchestration

- `oc-intent-clarify`
- `oc-review-situation`
- `oc-strategy-compare`
- `oc-context-discovery`
- `oc-plan-discovery`
- `oc-subagent-status-contract`

### 24.2 Setup/lifecycle

- `oc-setup`
- `oc-update`
- `oc-publish-pack`
- `oc-migrate-layout`
- `oc-doctor`
- `oc-generate-skill-catalog`

### 24.3 Planning/spec

- `oc-generate-spec`
- `oc-generate-plan`
- `oc-generate-phase-program`
- `oc-validate-contract`
- `oc-risk-evidence-pack`
- `oc-feasibility-probe`

### 24.4 Execution

- `oc-apply-surgical`
- `oc-minimal-change`
- `oc-code-economy`
- `oc-test-first`
- `oc-local-first-verification`

### 24.5 Diagnosis/self-healing

- `oc-autoresearch`
- `oc-root-cause-analysis`
- `oc-three-hypotheses`
- `oc-minimal-reproduction`
- `oc-instrumentation-first`
- `oc-plateau-detection`
- `oc-regression-detection`

### 24.6 Review/security

- `oc-code-review-grounded`
- `oc-security-review`
- `oc-scenario-risk`
- `oc-db-migration-safety`
- `oc-api-contract-review`
- `oc-performance-review`

### 24.7 Context/memory

- `oc-audit-context`
- `oc-context-splitter`
- `oc-context-refresh`
- `oc-memory-harvest`
- `oc-semantic-gc`
- `oc-project-knowledge-router`

### 24.8 Language/framework

- `oc-python-pytest-ruff-mypy`
- `oc-js-ts-eslint-vitest`
- `oc-php-phpunit-phpstan-phpcs`
- `oc-drupal-patterns`
- `oc-symfony-di`
- `oc-database-indexing`
- `oc-cms-architecture`

### 24.9 Docs/release/git

- `oc-technical-writer`
- `oc-docs-update`
- `oc-git-workflow`
- `oc-release-check`
- `oc-changelog`
- `oc-version-bump`

---

## 25. How these skills attach to SDD

### 25.1 SDD explore

Tier 0:

- intent clarify
- context discovery
- plan discovery
- review situation
- strategy compare

Tier 1:

- scout
- context envelope
- risk evidence if high impact

Output:

- context pack;
- L3 signatures;
- active plan refs;
- blast radius.

### 25.2 SDD spec

Tier 1:

- generate spec;
- requirements RFC2119;
- intent consistency.

Output:

- spec.md;
- acceptance criteria.

### 25.3 SDD design

Tier 1:

- design minimal;
- feasibility probe;
- architecture review.

Tier 2:

- security;
- database safety;
- performance.

### 25.4 SDD tasks

Tier 1:

- generate plan;
- task splitting;
- validate contract.

### 25.5 SDD apply

Tier 1:

- apply surgical;
- minimal change;
- test first if configured.

### 25.6 SDD verify

Tier 1:

- inspect local first;
- validate contract;
- autoresearch optional domain tests.

### 25.7 SDD review/archive

Tier 1:

- code review grounded;
- audit context if context changed;
- audit skills if skills changed;
- memory harvest;
- closeout.

---

## 26. How these skills attach to OC Flow

### 26.1 gather_context

- intent clarify abbreviated;
- context discovery;
- plan discovery abbreviated;
- review situation;
- strategy compare;
- scout.

### 26.2 plan

- plan lite;
- feasibility probe if needed;
- risk evidence if needed.

### 26.3 mutate

- minimal change;
- apply surgical;
- code economy;
- test first.

### 26.4 local_inspection

- local-first verification;
- syntax/lint/test;
- security scan;
- scenario risk if sensitive.

### 26.5 diagnose

- autoresearch domain tests/errors;
- root cause;
- three hypotheses;
- instrumentation;
- plateau detection;
- semantic GC.

### 26.6 escalation/consolidation

- owner handoff;
- closeout;
- memory harvest;
- context refresh;
- audit context if updated.

---

## 27. Skill quality scoring

Every skill receives a score.

```python
class SkillQualityScore(BaseModel):
    skill_id: str
    clarity: int
    token_efficiency: int
    safety: int
    specificity: int
    testability: int
    workflow_fit: int
    maintainability: int
    total: int
```

Minimum score to ship builtin:

```text
>= 80
```

Experimental:

```text
60-79
```

Reject:

```text
< 60
```

---

## 28. Skill benchmark

### 28.1 Benchmarks

```text
benchmarks/
  first_bugfix/
  sdd_small_feature/
  context_audit/
  skill_audit/
  php_drupal_fix/
  python_pytest_fix/
  js_ts_lint_fix/
```

### 28.2 Metrics

- success;
- tokens;
- time;
- changed lines;
- test pass;
- no scope creep;
- number of retries;
- correctness score;
- user-facing summary quality.

### 28.3 Skill regression

A skill update fails if:

- increases tokens >20% without quality gain;
- increases changed lines unexpectedly;
- fails first-run benchmark;
- produces invalid output contract;
- shadows another skill ambiguously.

---

## 29. Import pipeline for external inspirations

### 29.1 Process

```text
discover external skill/agent
  -> classify pattern
  -> extract useful behavior
  -> remove project/vendor-specific content
  -> rewrite as OpenContext skill
  -> define contract/gates
  -> add tests/benchmarks
  -> add to experimental
  -> graduate to builtin after benchmarks
```

### 29.2 Do not copy blindly

External repo material may include:

- different assumptions;
- tool-specific commands;
- project-specific content;
- unsafe update behavior;
- high token loops;
- incompatible status codes.

Everything must be normalized.

---

## 30. Complementary roadmap

### PR S1 — Skill contracts v2

- `SkillDefinition`;
- tiers;
- simple/deep mode;
- required outputs/gates.

### PR S2 — Builtin core skill bundle

- intent clarify;
- context discovery;
- plan discovery;
- review situation;
- strategy compare.

### PR S3 — Setup/update/publish lifecycle

- oc-setup;
- oc-update;
- oc-publish-pack;
- manifests;
- installed file snapshot.

### PR S4 — Audit validators

- audit skills;
- audit context;
- audit adapters;
- generated catalog.

### PR S5 — Autoresearch primitive

- plan/test/docs/context domains;
- plateau detection;
- iteration reports;
- EVL/PVL integration.

### PR S6 — Phase programs

- umbrella plans;
- phase plans;
- phase reports;
- current state.

### PR S7 — Adapter generation

- Claude/Codex/OpenCode surfaces;
- parity validation.

### PR S8 — Agency-inspired persona extensions

- database optimizer;
- git workflow;
- SRE;
- technical writer;
- CMS/Drupal specialist;
- minimal change engineer;
- multi-agent systems architect.

### PR S9 — Benchmarks

- first-run skill benchmarks;
- token regression tests;
- skill quality scores.

---

## 31. Definition of Done

This complementary plan is complete when:

- OpenContext has skill tiers.
- Every builtin skill has a contract.
- SDD and OC Flow load skill bundles.
- Setup creates useful project context.
- Context audit validates routing/discovery.
- Skill audit validates skill routing/dependencies/confusables.
- Update has dry-run and confirmation.
- Publish has leak detection.
- Autoresearch works for plan/tests/docs/context.
- Strategy compare selects low-cost safe execution.
- Subagent statuses are normalized.
- Multi-tool adapter surfaces are generated from one source.
- First-run benchmark improves success and token use.

---

## 32. Final recommendation

From `vibecode-pro-max-kit`, OpenContext should adopt:

```text
setup lifecycle
skill tiers
context audit
skill audit
manifest-driven update/publish
goal/autopilot resume
PVL/EVL autoresearch primitive
strategy comparison
subagent status protocol
phase programs
multi-tool compatibility
```

From `agency-agents`, OpenContext should adopt:

```text
specialist persona catalogue
clear when-to-use mapping
deliverable-oriented agent definitions
installable subsets
cross-tool conversion mindset
domain specialists for engineering, SRE, docs, DB, Git, CMS/Drupal
```

But OpenContext should make these stronger by adding:

```text
Knowledge Graph grounding
Context-as-Code
skill contracts
gates
receipts
event bus
runtime policies
token budgets
benchmarks
quality scores
```

This is the missing layer that can turn OpenContext from a good agentic runtime into a product that feels reliable on the first run.
