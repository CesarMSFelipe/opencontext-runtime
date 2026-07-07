# OpenContext — Plan completo corregido de cierre funcional, sistemas y pruebas reales

> Versión: 2.0 corregida  
> Propósito: convertir OpenContext en un runtime agéntico completo, verificable, mantenible y usable.  
> Corrección principal frente al plan anterior: SDD, TUI, configuración profunda, memoria, KG, compresión, harness, OC Flow, agentes, instalación/desinstalación y UX/DX aparecen como subsistemas explícitos con contratos, criterios de aceptación y pruebas reales.

---

## 0. Por qué este documento existe

El plan anterior era útil como dirección general, pero tenía un problema: no modelaba explícitamente todos los sistemas que ya forman parte de la visión de OpenContext.

Eso deja huecos peligrosos. Si SDD, TUI, configuración profunda, memoria, compresión, KG, harness, agentes, instalación/desinstalación y OC Flow no aparecen en el mapa principal, terminan quedando como añadidos laterales. En un runtime agéntico eso no puede ocurrir.

OpenContext debe cerrarse como producto integrado, no como suma de comandos.

La unidad de validación no será:

```text
"existe el comando"
```

sino:

```text
"el subsistema ejecuta su contrato, falla cuando debe fallar, deja evidencias y se integra con el resto del runtime"
```

---

## 1. Mapa completo del producto terminado

OpenContext debe organizarse alrededor de estos subsistemas canónicos.

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                              OpenContext Runtime                           │
├────────────────────────────────────────────────────────────────────────────┤
│  Surfaces                                                                  │
│  ├─ CLI                                                                    │
│  ├─ TUI                                                                    │
│  ├─ Agent adapters / IDE adapters / MCP adapters                           │
│  └─ Machine-readable JSON API via command contracts                         │
├────────────────────────────────────────────────────────────────────────────┤
│  Orchestration                                                             │
│  ├─ Harness                                                                │
│  ├─ OC Flow                                                                │
│  ├─ SDD Flow                                                               │
│  ├─ TDD Strict Engine                                                      │
│  ├─ Task lifecycle                                                         │
│  ├─ Gate engine                                                            │
│  └─ Resume / recovery engine                                               │
├────────────────────────────────────────────────────────────────────────────┤
│  Intelligence layer                                                        │
│  ├─ Context Pack Engine                                                    │
│  ├─ Compression Engine                                                     │
│  ├─ Knowledge Graph                                                        │
│  ├─ Memory System                                                          │
│  ├─ Decision Registry                                                      │
│  ├─ Policy Engine                                                          │
│  └─ Evidence Engine                                                        │
├────────────────────────────────────────────────────────────────────────────┤
│  Execution layer                                                           │
│  ├─ Executors                                                              │
│  │  ├─ test_stub                                                           │
│  │  ├─ patch executor                                                      │
│  │  ├─ shell executor                                                      │
│  │  ├─ provider-backed executor                                            │
│  │  └─ external agent executor                                             │
│  ├─ Tool registry                                                          │
│  ├─ Validator registry                                                     │
│  └─ Provider registry                                                      │
├────────────────────────────────────────────────────────────────────────────┤
│  Project integration                                                       │
│  ├─ Workspace installer/init                                               │
│  ├─ Config discovery and layering                                          │
│  ├─ Language/project detectors                                             │
│  ├─ Agent files generator                                                  │
│  ├─ Indexers                                                              │
│  └─ Cleanup/uninstall                                                      │
├────────────────────────────────────────────────────────────────────────────┤
│  Product lifecycle                                                         │
│  ├─ Global installation                                                    │
│  ├─ Global uninstallation                                                  │
│  ├─ Release validation                                                     │
│  ├─ Doctor/diagnostics                                                     │
│  ├─ Telemetry local/offline optional                                       │
│  └─ Migration/versioning                                                   │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Principio de cierre

OpenContext no estará terminado cuando todos los módulos existan. Estará terminado cuando se pueda demostrar esto:

```text
Dado un proyecto realista pero pequeño,
OpenContext puede instalarse, configurarse, indexar el código,
generar contexto mínimo, usar KG/memoria/compresión, ejecutar SDD u OC Flow,
aplicar TDD strict cuando proceda, mutar código con un executor,
verificar el cambio, guardar evidencias, actualizar memoria/KG,
mostrar el estado por CLI/TUI, reanudar si se interrumpe,
y desinstalarse sin residuos gestionados.
```

---

## 3. Fases de ejecución corregidas

### Fase 0 — Freeze y contrato único

#### Objetivo

Congelar el alcance del cierre para dejar de añadir piezas nuevas y empezar a cerrar flujos reales.

#### Cambios

1. Declarar un documento `PRODUCT_CONTRACT.md`.
2. Marcar todos los comandos como:
   - stable;
   - experimental;
   - deprecated;
   - internal.
3. Prohibir nuevos subsistemas hasta que pasen los acceptance tests.
4. Definir estados finales únicos para todo el runtime.

#### Estados finales canónicos

```text
passed
failed
blocked
needs_executor
needs_approval
needs_context
needs_configuration
not_applicable
cancelled
```

#### Criterios de aceptación

- Ningún comando stable puede devolver estados fuera de este catálogo.
- Ningún flujo puede devolver `passed` sin evidencias.
- Todo comando stable debe tener exit code definido.

---

### Fase 1 — Acceptance harness externo y real

#### Objetivo

Crear una suite black-box externa que pruebe OpenContext instalado como usuario real.

#### Regla

No debe importar módulos internos del runtime. Debe invocar el binario:

```bash
opencontext ...
```

#### Estructura recomendada

```text
acceptance/
├─ fixtures/
│  ├─ python_bugfix/
│  ├─ python_tdd_missing_red/
│  ├─ python_sdd_feature/
│  ├─ mixed_large_context/
│  ├─ config_matrix/
│  └─ tui_project/
├─ tests/
│  ├─ test_00_installation.py
│  ├─ test_01_cli_contracts.py
│  ├─ test_02_workspace_lifecycle.py
│  ├─ test_03_context_pack_kg_compression.py
│  ├─ test_04_memory_lifecycle.py
│  ├─ test_05_oc_flow.py
│  ├─ test_06_sdd_flow.py
│  ├─ test_07_tdd_strict.py
│  ├─ test_08_tui.py
│  ├─ test_09_deep_config.py
│  ├─ test_10_uninstall_purge.py
│  └─ test_11_release_gate.py
└─ README.md
```

#### Por qué así

Gentle AI y proyectos similares no suelen tener miles de tests internos absurdos. Tienen pruebas que validan el comportamiento real del producto, normalmente a través de interfaces públicas, snapshots/golden files y flujos completos.

OpenContext debe hacer lo mismo.

#### Tests mínimos reales

| Código | Flujo | Tipo |
|---|---|---|
| AC-001 | Instalar producto en entorno aislado | Black-box |
| AC-002 | `version --json` coincide con paquete | Contract |
| AC-003 | `init/install workspace` crea estado esperado | Black-box |
| AC-004 | `status --json` limpio y parseable | Contract |
| AC-005 | `index` crea KG mínimo | Black-box |
| AC-006 | `pack` usa KG y respeta budget | Black-box |
| AC-007 | `pack` aplica compresión medible | Black-box |
| AC-008 | `memory save/search/get` funciona | Black-box |
| AC-009 | memoria se reutiliza en una segunda run | E2E |
| AC-010 | OC Flow sin executor devuelve `needs_executor` | Black-box |
| AC-011 | OC Flow con executor muta y verifica | E2E |
| AC-012 | OC Flow con mutación mala falla | Regression |
| AC-013 | TDD strict falla sin RED test | Regression |
| AC-014 | TDD strict pasa solo RED → GREEN | E2E |
| AC-015 | SDD `new → propose → spec → design → tasks → apply → verify → archive` funciona | E2E |
| AC-016 | SDD no pierde artefactos entre comandos | Regression |
| AC-017 | TUI arranca, navega y ejecuta flujo read-only | TUI |
| AC-018 | TUI muestra run fallida correctamente | TUI |
| AC-019 | Config profunda resuelve precedencia correctamente | Contract |
| AC-020 | Config inválida falla con diagnóstico útil | Contract |
| AC-021 | `doctor --json` detecta problemas reales | Black-box |
| AC-022 | `uninstall workspace --purge --verify` limpia workspace | Black-box |
| AC-023 | `uninstall product --purge --verify` limpia instalación gestionada | Black-box |
| AC-024 | release gate instala desde paquete limpio y pasa smoke | Release |
| AC-025 | no hay texto humano mezclado en stdout JSON | Contract |

Cantidad inicial: 25 tests reales. No más hasta que estos pasen.

---

## 4. Fase 2 — CLI como API estable

### Objetivo

Normalizar todos los comandos públicos como contratos estables.

### Comandos stable obligatorios

```bash
opencontext version
opencontext doctor
opencontext status
opencontext init
opencontext install
opencontext uninstall
opencontext config
opencontext index
opencontext pack
opencontext run
opencontext sdd
opencontext harness
opencontext memory
opencontext knowledge-graph
opencontext tui
```

### Flags globales obligatorias

Todo comando stable debe soportar cuando aplique:

```bash
--json
--quiet
--verbose
--root <path>
--config <path>
--profile <name>
--dry-run
--verify
--no-color
```

### Contrato JSON común

Todo JSON debe tener:

```json
{
  "schema_version": "v1",
  "command": "opencontext <command>",
  "status": "passed|failed|blocked|needs_executor|...",
  "exit_code": 0,
  "root": "/path",
  "started_at": "ISO-8601",
  "finished_at": "ISO-8601",
  "duration_ms": 123,
  "summary": "...",
  "data": {},
  "warnings": [],
  "errors": [],
  "evidence": {}
}
```

### Criterios de aceptación

- `--json` no mezcla texto humano por stdout.
- Todo error machine-readable incluye código estable.
- Exit code coincide con `status`.
- Los comandos experimentales no aparecen como stable en help principal.

---

## 5. Fase 3 — TUI como superficie real del producto

### Objetivo

El TUI no debe ser decorativo. Debe permitir operar y depurar el runtime.

### Pantallas mínimas

```text
Dashboard
Runs
Run detail
Context pack viewer
Knowledge graph viewer
Memory viewer
SDD workspace
TDD gate viewer
Config inspector
Doctor diagnostics
Uninstall preview
```

### Flujos TUI obligatorios

#### TUI-001 — Arranque y diagnóstico

```text
opencontext tui
→ detecta workspace
→ muestra status
→ muestra problemas de doctor
→ permite abrir configuración efectiva
```

#### TUI-002 — Ver una run

```text
Runs
→ seleccionar run
→ ver fases
→ ver gates
→ ver evidencias
→ ver logs
→ ver changed files
```

#### TUI-003 — Context pack

```text
Pack viewer
→ muestra archivos incluidos
→ símbolos incluidos
→ memoria incluida
→ edges KG usados
→ tokens estimados
→ compresión aplicada
```

#### TUI-004 — SDD

```text
SDD workspace
→ lista specs
→ muestra fase actual
→ muestra artefactos propose/spec/design/tasks
→ permite ejecutar siguiente fase si no requiere aprobación
```

#### TUI-005 — Memoria

```text
Memory viewer
→ lista memorias
→ filtra por tipo
→ muestra confianza/caducidad/origen
→ permite aprobar/rechazar memoria pendiente
```

#### TUI-006 — Config

```text
Config inspector
→ muestra config efectiva
→ origen de cada valor
→ validación
→ conflictos
→ overrides activos
```

#### TUI-007 — Uninstall preview

```text
Uninstall
→ muestra rutas gestionadas
→ muestra residuos posibles
→ dry-run
→ confirmación
```

### Cómo probar el TUI sin tests raros

No hace falta probar cada pixel ni cada tecla interna. Se prueban contratos de comportamiento.

#### Herramienta

Usar una librería tipo `pexpect`, snapshot textual estable o runner del framework TUI si existe.

#### Tests TUI reales

| Código | Prueba |
|---|---|
| TUI-AC-001 | `opencontext tui --smoke` arranca y sale con `q` |
| TUI-AC-002 | Dashboard muestra workspace detectado |
| TUI-AC-003 | Run detail muestra fases y status |
| TUI-AC-004 | Config inspector muestra precedencia |
| TUI-AC-005 | SDD screen muestra artefactos existentes |
| TUI-AC-006 | Memory screen muestra memoria guardada |
| TUI-AC-007 | TUI no rompe en terminal pequeño |
| TUI-AC-008 | TUI muestra error legible si no hay workspace |

No probar implementación interna del TUI. Probar que el usuario puede ver y operar los estados importantes.

---

## 6. Fase 4 — Configuración profunda

### Objetivo

OpenContext debe tener una configuración potente, pero predecible y depurable.

### Capas de configuración

Orden de menor a mayor precedencia:

```text
1. defaults internos
2. config global
3. config de organización/equipo
4. config de workspace
5. profile seleccionado
6. variables de entorno
7. flags CLI
8. overrides temporales de run
```

### Comando obligatorio

```bash
opencontext config explain --json
```

Debe devolver:

```json
{
  "effective_config": {},
  "sources": {
    "runtime.oc_flow.enabled": {
      "value": true,
      "source": "workspace",
      "path": "opencontext.yaml",
      "line": 12
    }
  },
  "conflicts": [],
  "deprecated_keys": [],
  "unknown_keys": [],
  "validation": {
    "status": "passed"
  }
}
```

### Perfiles

```yaml
profiles:
  default:
    executor: test_stub
    tdd_mode: strict

  ci:
    interactive: false
    tui: false
    json: true

  local:
    interactive: true
    tui: true

  agent:
    approval_mode: required
    context_budget_tokens: 24000
```

### Config mínima canónica

```yaml
runtime:
  schema_version: v1
  mode: local
  oc_flow:
    enabled: true
  sdd:
    enabled: true
  harness:
    enabled: true

context:
  budget_tokens: 24000
  pack:
    strategy: kg_memory_tests
  compression:
    enabled: true
    strategy: protected_spans
    target_ratio: 0.45

knowledge_graph:
  enabled: true
  backend: sqlite
  include_tests: true
  include_docs: true

memory:
  enabled: true
  provider: local
  approval_required: true
  store_raw: false
  retention_days: 90

tdd:
  mode: strict
  require_red: true
  require_green: true

executors:
  default: test_stub
  allow_shell: false

tui:
  enabled: true

uninstall:
  manifest_required: true
```

### Tests reales de configuración

| Código | Prueba |
|---|---|
| CFG-001 | workspace override gana a global |
| CFG-002 | ENV gana a workspace |
| CFG-003 | CLI flag gana a ENV |
| CFG-004 | profile `ci` desactiva interactividad |
| CFG-005 | key desconocida genera warning |
| CFG-006 | config inválida falla con error útil |
| CFG-007 | `config explain` indica fuente de cada valor |
| CFG-008 | migración de config antigua produce aviso |
| CFG-009 | secret no se imprime en JSON |
| CFG-010 | configuración TDD se propaga a harness y SDD |

---

## 7. Fase 5 — Harness como núcleo real

### Objetivo

El harness debe ser el orquestador verificable.

### Contrato

```text
input task
→ resolve config
→ create run
→ build context
→ run phase plan
→ enforce gates
→ execute mutation if allowed
→ verify
→ collect evidence
→ update KG
→ propose memory delta
→ finalize report
```

### Artefactos obligatorios por run

```text
.opencontext/runs/<run_id>/
├─ manifest.json
├─ input.json
├─ effective_config.json
├─ context_pack.json
├─ plan.json
├─ phases/
│  ├─ explore.json
│  ├─ propose.json
│  ├─ spec.json
│  ├─ design.json
│  ├─ tasks.json
│  ├─ apply.json
│  ├─ verify.json
│  └─ review.json
├─ gates.json
├─ commands.json
├─ diff.patch
├─ verification.json
├─ memory_delta.json
├─ graph_delta.json
├─ report.json
└─ logs/
```

### Gates obligatorias

```text
config_valid
workspace_valid
context_pack_created
kg_available_or_declared_absent
memory_policy_checked
executor_policy_checked
approval_checked
tdd_red_required_if_strict
mutation_required_if_task_requires_change
mutation_detected_if_required
verification_command_executed
verification_passed
json_contract_valid
evidence_complete
```

### Criterios de aceptación

- El harness no puede devolver `passed` si una gate obligatoria falla.
- Un flujo de implementación sin mutación debe fallar o devolver `needs_executor`.
- Un flujo con tests fallidos debe devolver `failed`.
- Cada gate debe tener evidencia.

---

## 8. Fase 6 — SDD como flujo completo

### Objetivo

SDD debe ser un sistema de trabajo real, no un conjunto de placeholders.

### Comandos obligatorios

```bash
opencontext sdd init
opencontext sdd new
opencontext sdd explore
opencontext sdd propose
opencontext sdd spec
opencontext sdd design
opencontext sdd tasks
opencontext sdd apply
opencontext sdd verify
opencontext sdd review
opencontext sdd archive
opencontext sdd status
opencontext sdd continue
```

### Artefactos SDD obligatorios

```text
.opencontext/sdd/
├─ registry.json
├─ specs/
│  └─ <spec_id>/
│     ├─ manifest.json
│     ├─ problem.md
│     ├─ exploration.md
│     ├─ proposal.md
│     ├─ specification.md
│     ├─ design.md
│     ├─ tasks.md
│     ├─ acceptance.md
│     ├─ runs/
│     └─ archive/
```

### Máquina de estados SDD

```text
draft
explored
proposed
specified
designed
tasked
applying
verified
reviewed
archived
blocked
failed
```

### Reglas

- `sdd new` crea un spec_id persistente.
- Cada fase lee la fase anterior.
- Ninguna fase puede perder artefactos.
- `sdd apply` usa el mismo harness que OC Flow.
- `sdd verify` usa el mismo engine de verificación.
- Si TDD strict está activo, SDD apply debe cumplir RED → GREEN.
- `sdd continue` reanuda desde la última fase incompleta.
- `sdd status --json` muestra fase actual, gates y próximos pasos.

### Tests reales SDD

| Código | Prueba |
|---|---|
| SDD-001 | `sdd init` crea estructura |
| SDD-002 | `sdd new` crea spec persistente |
| SDD-003 | `sdd propose` lee `exploration.md` |
| SDD-004 | `sdd spec` lee proposal y produce acceptance |
| SDD-005 | `sdd design` produce diseño trazable |
| SDD-006 | `sdd tasks` produce tareas ejecutables |
| SDD-007 | `sdd apply` usa harness y genera run |
| SDD-008 | `sdd verify` falla si tests fallan |
| SDD-009 | `sdd continue` reanuda correctamente |
| SDD-010 | `sdd archive` cierra y conserva evidencias |
| SDD-011 | SDD con TDD strict exige RED → GREEN |
| SDD-012 | SDD aparece correctamente en TUI |

---

## 9. Fase 7 — TDD strict real

### Objetivo

Eliminar falsos positivos. TDD strict debe demostrar ciclo RED → GREEN.

### Contrato

```text
1. detectar o crear test candidato
2. ejecutar test antes del cambio
3. comprobar que falla por la razón esperada
4. aplicar mutación
5. ejecutar test después del cambio
6. comprobar que pasa
7. ejecutar suite/regresión mínima
8. registrar evidencia
```

### JSON de evidencia

```json
{
  "tdd": {
    "mode": "strict",
    "red": {
      "command": "pytest tests/test_app.py::test_add -q",
      "exit_code": 1,
      "failed": true,
      "failure_signature": "assert -1 == 3"
    },
    "green": {
      "command": "pytest tests/test_app.py::test_add -q",
      "exit_code": 0,
      "passed": true
    },
    "regression": {
      "command": "pytest -q",
      "exit_code": 0
    }
  }
}
```

### Criterios

- Si no hay RED, no hay `passed`.
- Si no hay GREEN, no hay `passed`.
- Si no hubo mutación y la tarea requería cambio, no hay `passed`.
- Si el test ya pasaba antes, no cuenta como RED.

### Tests reales TDD

| Código | Prueba |
|---|---|
| TDD-001 | falla sin test |
| TDD-002 | falla si test pasa antes |
| TDD-003 | falla si mutación no ocurre |
| TDD-004 | falla si GREEN no pasa |
| TDD-005 | pasa con RED → GREEN real |
| TDD-006 | evidencia RED/GREEN queda en report |
| TDD-007 | SDD respeta TDD strict |
| TDD-008 | OC Flow respeta TDD strict |

---

## 10. Fase 8 — OC Flow cerrado

### Objetivo

OC Flow debe ser un flujo agéntico honesto y usable.

### Fases

```text
init
gather_context
plan
approval
mutate
local_inspection
verify
repair_loop
memory_update
kg_update
consolidation
```

### Estados esperados

| Situación | Estado |
|---|---|
| tarea no requiere cambios | `passed` con `mutation_required=false` |
| tarea requiere cambios sin executor | `needs_executor` |
| executor aplica cambio y tests pasan | `passed` |
| executor aplica cambio y tests fallan | `failed` |
| requiere aprobación | `needs_approval` |
| falta configuración | `needs_configuration` |
| contexto insuficiente | `needs_context` |

### Tests reales OC Flow

| Código | Prueba |
|---|---|
| OC-001 | sin executor devuelve `needs_executor` |
| OC-002 | con executor correcto muta y verifica |
| OC-003 | con executor malo falla |
| OC-004 | sin config necesaria devuelve `needs_configuration` |
| OC-005 | con TDD strict exige RED/GREEN |
| OC-006 | genera memory_delta y graph_delta |
| OC-007 | reporta tokens, KG y memoria usados |
| OC-008 | se ve correctamente en TUI |

---

## 11. Fase 9 — Knowledge Graph

### Objetivo

El KG debe ahorrar tokens y mejorar precisión, no solo buscar símbolos.

### Nodos mínimos

```text
file
symbol
test
module
command
config_key
memory
decision
artifact
run
task
spec
```

### Edges mínimos

```text
defines
calls
imports
tests
depends_on
documents
configured_by
produced_by
modified_by
related_to
implements
verifies
```

### Comandos

```bash
opencontext knowledge-graph build
opencontext knowledge-graph search
opencontext knowledge-graph explain
opencontext knowledge-graph neighbors
opencontext knowledge-graph stats
opencontext knowledge-graph prune
```

### Contrato de `pack`

El pack debe poder decir:

```json
{
  "kg": {
    "used": true,
    "nodes_selected": 12,
    "edges_used": 18,
    "test_nodes_included": 2,
    "reason": "symbols related to query and failing tests"
  }
}
```

### Tests KG reales

| Código | Prueba |
|---|---|
| KG-001 | index detecta archivo, símbolo y test |
| KG-002 | edge `tests` conecta test con símbolo |
| KG-003 | `pack` incluye test relacionado por KG |
| KG-004 | cambio de archivo actualiza KG |
| KG-005 | KG no indexa basura/caches |
| KG-006 | `kg explain` justifica selección |
| KG-007 | uninstall purga KG local |
| KG-008 | TUI muestra nodos y edges básicos |

---

## 12. Fase 10 — Context Pack y compresión

### Objetivo

Reducir tokens sin perder información crítica.

### Pipeline

```text
task query
→ project detection
→ KG ranking
→ test discovery
→ memory recall
→ config awareness
→ file/symbol slicing
→ protected span detection
→ compression
→ budget allocation
→ final pack
```

### Protected spans

No se pueden comprimir agresivamente:

```text
funciones objetivo
tests relevantes
interfaces públicas
config efectiva
errores
decisiones recientes
contratos JSON
```

### Métricas obligatorias

```json
{
  "context": {
    "budget_tokens": 24000,
    "estimated_input_tokens": 81200,
    "estimated_output_tokens": 18500,
    "compression_ratio": 0.22,
    "kg_used": true,
    "memory_hits": 3,
    "protected_spans": {
      "count": 9,
      "kept": 9
    }
  }
}
```

### Tests reales

| Código | Prueba |
|---|---|
| CTX-001 | pack respeta budget |
| CTX-002 | pack incluye test relacionado |
| CTX-003 | pack incluye memoria relevante |
| CTX-004 | compresión reduce tokens mediblemente |
| CTX-005 | protected spans se conservan |
| CTX-006 | pack explica por qué incluyó/excluyó archivos |
| CTX-007 | proyecto grande no mete todo el repo |
| CTX-008 | TUI muestra pack y métricas |

---

## 13. Fase 11 — Memoria agéntica

### Objetivo

Memoria debe ser reutilizable, auditable y purgable.

### Tipos

```text
fact
decision
preference
project_rule
learned_pattern
error_resolution
summary
```

### Ciclo

```text
capture
classify
deduplicate
approval
store
retrieve
use
decay
summarize
purge
```

### Comandos

```bash
opencontext memory init
opencontext memory save
opencontext memory search
opencontext memory get
opencontext memory list
opencontext memory approve
opencontext memory reject
opencontext memory compact
opencontext memory doctor
opencontext memory purge
```

### Evidencia de uso

Una run que usa memoria debe reportar:

```json
{
  "memory": {
    "used": true,
    "hits": [
      {
        "id": "mem_123",
        "type": "project_rule",
        "score": 0.91,
        "used_for": "test command selection"
      }
    ],
    "new_candidates": 2,
    "requires_approval": true
  }
}
```

### Tests reales

| Código | Prueba |
|---|---|
| MEM-001 | save/search/get |
| MEM-002 | memoria pendiente requiere aprobación |
| MEM-003 | memoria aprobada se usa en segunda run |
| MEM-004 | memoria no relevante no se usa |
| MEM-005 | memoria duplicada se deduplica |
| MEM-006 | compact genera resumen |
| MEM-007 | purge elimina todo |
| MEM-008 | uninstall purga memoria gestionada |
| MEM-009 | TUI permite ver/aprobar/rechazar |

---

## 14. Fase 12 — Agentes, executors y policies

### Objetivo

Separar claramente planificación, ejecución, permisos y verificación.

### Executors

```text
test_stub
patch
shell
provider
external_agent
manual
```

### Policies

```yaml
policies:
  writes:
    require_approval: true
  shell:
    allow: false
  network:
    allow: false
  secrets:
    redact: true
  destructive_actions:
    require_explicit_confirmation: true
```

### Contrato

Un executor debe declarar:

```json
{
  "name": "test_stub",
  "can_mutate": true,
  "can_run_shell": false,
  "requires_approval": false,
  "supported_languages": ["python"]
}
```

### Tests

| Código | Prueba |
|---|---|
| EXE-001 | executor no permitido bloquea mutación |
| EXE-002 | shell deshabilitado bloquea comandos |
| EXE-003 | provider ausente devuelve `needs_executor` |
| EXE-004 | patch executor aplica diff |
| EXE-005 | acciones destructivas requieren aprobación |
| EXE-006 | secrets no aparecen en logs/report |

---

## 15. Fase 13 — Instalación y desinstalación

### Objetivo

Instalación global y workspace separadas. Desinstalación sin residuos gestionados.

### Comandos

```bash
opencontext install product
opencontext install workspace
opencontext install agents

opencontext uninstall workspace --purge --verify
opencontext uninstall product --purge --verify
opencontext uninstall agents --purge --verify
```

### Manifest

Cada instalación debe escribir:

```json
{
  "schema_version": "v1",
  "install_id": "...",
  "method": "pipx|pip|uv|script|brew|manual",
  "version": "1.6.x",
  "created_paths": [],
  "modified_files": [],
  "shell_profile_blocks": [],
  "symlinks": [],
  "agent_configs": [],
  "state_paths": []
}
```

### Tests reales

| Código | Prueba |
|---|---|
| INST-001 | instalación product registra manifest |
| INST-002 | instalación workspace registra manifest |
| INST-003 | reinstall idempotente |
| INST-004 | uninstall workspace limpia workspace |
| INST-005 | uninstall product limpia paths gestionados |
| INST-006 | uninstall dry-run no borra |
| INST-007 | uninstall verify detecta residuo |
| INST-008 | no borra archivos no gestionados |
| INST-009 | TUI muestra preview de uninstall |

---

## 16. Estrategia de tests ligera pero real

### Lo que NO se debe hacer

```text
- tests sobre cada método interno sin contrato
- tests duplicados por cada comando si ya hay black-box
- tests de mocks que solo prueban mocks
- tests que obligan a mantener implementación accidental
- tests gigantes lentos que nadie ejecuta
- tests de snapshots inestables sin valor
```

### Lo que SÍ se debe hacer

```text
- acceptance black-box
- golden JSON contracts
- unit tests de algoritmos críticos
- integration tests de fronteras reales
- regression tests de bugs P0/P1
- TUI smoke/contract tests
- config resolution tests
- release install tests
```

### Distribución recomendada

| Capa | Cantidad objetivo | Qué protege |
|---|---:|---|
| Acceptance black-box | 25–40 | Producto real |
| Golden contracts | 20–30 | CLI/JSON estable |
| Unit core | 80–150 | Algoritmos críticos |
| Integration narrow | 25–50 | FS, config, KG, memory |
| TUI smoke | 6–10 | Superficie visual real |
| Regression | Según bugs | No repetir P0/P1 |

### Pirámide adaptada a OpenContext

```text
                ┌──────────────────────┐
                │  Release smoke       │ 5-8
                ├──────────────────────┤
                │  Acceptance E2E      │ 25-40
                ├──────────────────────┤
                │  Golden contracts    │ 20-30
                ├──────────────────────┤
                │  Integration narrow  │ 25-50
                ├──────────────────────┤
                │  Unit core           │ 80-150
                └──────────────────────┘
```

No hace falta una montaña de tests. Hace falta que los tests importantes sean implacables.

---

## 17. Tests por subsistema

| Subsistema | Acceptance | Golden | Unit core | Integration | TUI |
|---|---:|---:|---:|---:|---:|
| CLI | 6 | 15 | 5 | 5 | 0 |
| TUI | 4 | 2 | 5 | 2 | 8 |
| Config | 4 | 5 | 15 | 6 | 1 |
| Install/uninstall | 5 | 2 | 5 | 8 | 1 |
| Harness | 5 | 5 | 20 | 8 | 2 |
| OC Flow | 5 | 3 | 10 | 5 | 1 |
| SDD | 6 | 5 | 15 | 8 | 2 |
| TDD | 4 | 2 | 10 | 4 | 1 |
| KG | 4 | 2 | 20 | 8 | 1 |
| Context/compression | 5 | 3 | 25 | 6 | 1 |
| Memory | 5 | 3 | 15 | 8 | 2 |
| Executors/policy | 4 | 3 | 15 | 5 | 0 |
| Release | 3 | 1 | 0 | 5 | 0 |

El total no debe crecer sin control. Si se añade un test nuevo, debe responder a una de estas preguntas:

```text
1. ¿protege un contrato público?
2. ¿evita un bug real?
3. ¿valida una decisión crítica?
4. ¿demuestra un flujo de usuario/agente?
5. ¿protege un algoritmo donde un error sería caro?
```

Si no, no se añade.

---

## 18. Orden exacto de implementación

### Sprint A — Contratos y acceptance harness

1. Crear `PRODUCT_CONTRACT.md`.
2. Crear `acceptance/`.
3. Añadir fixtures mínimas.
4. Implementar AC-001 a AC-010.
5. Configurar CI para ejecutar acceptance desde paquete instalado.

Salida esperada:

```text
tests fallan de forma útil
sabemos exactamente qué está roto
```

### Sprint B — CLI/JSON/exit codes

1. Normalizar response envelope.
2. Arreglar stdout JSON.
3. Arreglar exit codes.
4. Ocultar comandos experimentales.
5. Añadir golden tests.

Salida:

```text
todo comando stable dice la verdad
```

### Sprint C — Config profunda

1. Implementar config layering.
2. Implementar `config explain`.
3. Añadir profiles.
4. Propagar TDD/SDD/harness config.
5. Añadir tests CFG.

Salida:

```text
no hay drift entre configuraciones
```

### Sprint D — Harness real

1. Rediseñar run manifest.
2. Gates obligatorias.
3. Evidencias.
4. Reports.
5. Resume base.

Salida:

```text
no hay success without evidence
```

### Sprint E — TDD strict

1. Implementar RED/GREEN engine.
2. Integrarlo con harness.
3. Integrarlo con OC Flow.
4. Integrarlo con SDD.
5. Añadir regression tests.

Salida:

```text
TDD strict significa TDD real
```

### Sprint F — OC Flow

1. Estados cerrados.
2. needs_executor correcto.
3. mutation detection.
4. verification strict.
5. memory/KG deltas.

Salida:

```text
OC Flow cerrado E2E
```

### Sprint G — SDD

1. Conectar todos los comandos.
2. Persistir spec registry.
3. Artefactos por fase.
4. `continue`.
5. Integración TUI.

Salida:

```text
SDD operativo real
```

### Sprint H — KG/context/compression

1. Enriquecer nodos/edges.
2. Pack explainable.
3. Protected spans.
4. Métricas de compresión.
5. Tests de ahorro tokens.

Salida:

```text
OpenContext ahorra tokens demostrablemente
```

### Sprint I — Memoria

1. Ciclo pending/approved.
2. Reutilización en segunda run.
3. Compactación.
4. Purga.
5. TUI memory viewer.

Salida:

```text
memoria agéntica real
```

### Sprint J — TUI

1. Dashboard.
2. Runs.
3. SDD.
4. Config.
5. Memory.
6. KG/Context.
7. Uninstall preview.

Salida:

```text
el usuario puede entender y operar OpenContext
```

### Sprint K — Install/uninstall

1. Separar product/workspace/agents.
2. Manifest.
3. Purge.
4. Verify.
5. No borrar no gestionado.

Salida:

```text
instalación y desinstalación fiables
```

### Sprint L — Release gate

1. Build limpio.
2. Install desde paquete publicado.
3. Acceptance completa.
4. Evidence bundle.
5. Release checklist.

Salida:

```text
no se publica si no pasa el producto real
```

---

## 19. Definition of Done final

OpenContext estará terminado cuando:

```text
1. El paquete publicado se instala en entorno limpio.
2. version/status/doctor/config son consistentes.
3. workspace init/install funciona.
4. index crea KG.
5. pack usa KG, memoria y compresión con métricas.
6. OC Flow funciona con y sin executor.
7. SDD completo funciona de new a archive.
8. TDD strict demuestra RED → GREEN.
9. memoria se guarda, aprueba, reutiliza, compacta y purga.
10. TUI permite ver y operar runs, SDD, config, memory, KG y uninstall.
11. config explain muestra precedencia exacta.
12. uninstall workspace/product/agents purga residuos gestionados.
13. acceptance harness externo pasa desde paquete instalado.
14. los exit codes son fiables.
15. no hay JSON sucio.
16. no hay comandos stable placeholder.
17. release genera evidencias.
```

---

## 20. Conclusión

El plan corregido no intenta añadir más complejidad. Intenta hacer visible todo lo que ya forma parte de la promesa de OpenContext.

La diferencia crítica es que ahora SDD, TUI, configuración profunda, memoria, KG, compresión, harness, OC Flow, TDD, agentes, instalación y desinstalación son subsistemas de primer nivel.

Y los tests no se multiplican sin sentido. Se reducen a pruebas reales que validan contratos de producto.

La regla final:

```text
Si un subsistema aparece en la promesa de OpenContext,
debe aparecer en el mapa,
debe tener contrato,
debe tener flujo,
debe tener evidencia,
debe tener prueba black-box o contract test,
y debe verse en CLI/TUI cuando sea relevante.
```
