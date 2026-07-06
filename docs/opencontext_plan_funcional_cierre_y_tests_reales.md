# OpenContext — Plan completo de cierre funcional y estrategia de tests reales

> Estado del documento: plan operativo de ejecución.  
> Objetivo: convertir OpenContext en un runtime agéntico funcional, verificable, mantenible y usable.  
> Principio rector: **OpenContext no está terminado cuando tiene comandos; está terminado cuando un harness externo demuestra que esos comandos cumplen su contrato, fallan cuando deben fallar y dejan evidencias verificables.**

---

## 0. Resumen ejecutivo

OpenContext debe dejar de evolucionar por acumulación de funcionalidades y pasar a evolucionar por **contratos de comportamiento**. El producto ideal no es solo un CLI con módulos de SDD, TDD, memoria, grafo y compresión. Es un sistema agéntico que ayuda a trabajar de forma organizada, ahorra tokens, mantiene conocimiento entre ejecuciones, aplica cambios con verificación y permite auditar todo el proceso.

El plan se divide en dos movimientos principales:

1. **Cerrar funcionalmente el producto**: contratos, estados, CLI, harness, TDD real, SDD conectado, OC Flow, memoria, KG, compresión, instalación/desinstalación y release.
2. **Rehacer la estrategia de tests**: menos tests, pero más reales; estilo black-box/golden/fixtures, más parecido a proyectos como Gentle AI, donde los tests validan el producto y no detalles accidentales de implementación.

El objetivo no es tener cientos o miles de tests frágiles. El objetivo es tener una suite pequeña, clara, externa, reproducible y con mucha señal.

---

## 1. Problema actual

### 1.1 Síntoma

Después de muchas iteraciones, el sistema sigue sin sentirse cerrado porque varias piezas existen, pero no están obligadas a demostrar comportamiento real de extremo a extremo.

Ejemplos de síntomas típicos:

- comandos que existen pero no están conectados a un flujo funcional completo;
- estados `passed` o `warning` aunque no hubo mutación real;
- TDD `strict` declarado, pero sin prueba RED → GREEN obligatoria;
- memoria que guarda y busca, pero no demuestra reutilización en una ejecución posterior;
- grafo que indexa símbolos, pero no demuestra ahorro real de tokens ni mejora del pack;
- compresión configurada, pero sin medición bajo presión de contexto;
- uninstall que limpia estado de workspace, pero no garantiza purga total del producto;
- tests internos que prueban detalles concretos, pero no validan que el usuario pueda usar el producto.

### 1.2 Causa raíz

La causa raíz no es falta de ideas. Es falta de una frontera dura entre:

```text
funcionalidad que existe nominalmente
```

y:

```text
funcionalidad que ha sido demostrada por una prueba externa y reproducible
```

El producto necesita una política estricta:

```text
Si no hay evidencia, no está hecho.
Si no hay verificación, no está hecho.
Si el estado final no coincide con la realidad, es P0.
Si el test no representa un comportamiento de usuario/agente, probablemente sobra.
```

---

## 2. Objetivo funcional final

OpenContext debe ser un runtime local-first para trabajo agéntico sobre repositorios. Su valor principal es permitir que un agente o usuario pueda ejecutar tareas complejas con menos contexto, más orden y más verificabilidad.

### 2.1 Capacidades finales obligatorias

| Área | Estado final esperado |
|---|---|
| CLI | API estable para humanos y agentes, con JSON limpio, exit codes fiables y mensajes accionables. |
| Harness | Orquestador real de fases, gates, artefactos, evidencias, reanudación y reporting. |
| OC Flow | Flujo rápido de trabajo agéntico: contexto → plan → mutación → verificación → memoria/KG → reporte. |
| SDD | Ciclo completo: explore → propose → spec → design → tasks → apply → verify → archive. |
| TDD strict | RED → GREEN probado, no declarado. Si no hay RED válido, falla. |
| Memoria | Captura, aprobación, búsqueda, reutilización, compacción, caducidad y purga. |
| Knowledge Graph | Grafo útil para impacto, selección de contexto, tests relacionados y ahorro de tokens. |
| Compresión | Reducción observable de contexto sin perder spans protegidos. |
| Instalación | Separación clara entre producto, workspace y agentes. |
| Desinstalación | Purga total de estado gestionado y, si aplica, instalación global mediante manifest. |
| Release | Paquete limpio, reproducible, testeado desde instalación real. |
| Tests | Pocos, reales, mantenibles, black-box donde importa y unitarios solo donde aportan señal. |

---

## 3. Principios de ejecución

### 3.1 Freeze de scope

Antes de ejecutar el plan se congela el scope.

No se permite añadir:

- nuevos providers;
- nuevos comandos decorativos;
- nuevos modos experimentales;
- nuevas abstracciones sin uso;
- integraciones extra;
- features no cubiertas por un escenario de aceptación.

Solo se permite trabajo que cierre una capacidad existente o necesaria para el contrato final.

### 3.2 Progreso medido por aceptación, no por implementación

No se considera avance:

```text
"he creado el módulo"
"el comando ya existe"
"devuelve JSON"
"pasa un test unitario interno"
```

Sí se considera avance:

```text
AC-012 pasa desde una instalación limpia del paquete publicado.
AC-012 falla si rompo intencionadamente la condición que protege.
AC-012 deja evidencias en report.json y devuelve exit code correcto.
```

### 3.3 Menos tests, más señal

La suite debe ser pequeña y real.

Regla:

```text
Cada test debe proteger un contrato de producto, un algoritmo crítico o una regresión real.
```

Si un test no cumple eso, se elimina o se convierte en caso de aceptación más alto nivel.

---

# PARTE I — PLAN DE EJECUCIÓN FUNCIONAL

---

## 4. Fase 0 — Contrato único de producto

### 4.1 Objetivo

Crear una frontera canónica de qué significa que OpenContext esté completo. Esta fase evita que cada iteración cambie el significado de “funciona”.

### 4.2 Cambios

Crear o consolidar estos documentos en `docs/product-contract/`:

```text
docs/product-contract/
├── PRODUCT_CONTRACT.md
├── CLI_CONTRACT.md
├── RUN_STATE_CONTRACT.md
├── ACCEPTANCE_CONTRACT.md
├── INSTALL_UNINSTALL_CONTRACT.md
├── TDD_STRICT_CONTRACT.md
├── SDD_CONTRACT.md
├── MEMORY_CONTRACT.md
├── KG_CONTEXT_COMPRESSION_CONTRACT.md
└── RELEASE_CONTRACT.md
```

No deben ser documentos largos aspiracionales. Deben ser contratos ejecutables y trazables.

### 4.3 Contenido mínimo

`PRODUCT_CONTRACT.md` define:

- qué es OpenContext;
- qué es stable, preview e internal;
- qué comandos son públicos;
- qué flujos son obligatorios;
- qué estados finales existen;
- qué evidencia debe generarse;
- qué significa producto terminado.

`CLI_CONTRACT.md` define:

- flags globales;
- JSON limpio;
- estructura de error;
- exit codes;
- compatibilidad semver;
- comandos stable/preview/internal.

`RUN_STATE_CONTRACT.md` define los únicos estados válidos:

```text
passed
failed
blocked
needs_executor
needs_approval
needs_context
not_applicable
cancelled
```

Y sus reglas:

| Estado | Puede tener exit 0 | Significado |
|---|---:|---|
| `passed` | Sí | Todo lo obligatorio pasó con evidencia. |
| `failed` | No | Una verificación obligatoria falló. |
| `blocked` | No | No se pudo continuar por falta de config, permisos o precondición. |
| `needs_executor` | Según comando | La tarea requiere executor/modelo y no hay uno productivo. |
| `needs_approval` | Según comando | La policy requiere aprobación humana. |
| `needs_context` | No | El sistema no pudo construir contexto suficiente. |
| `not_applicable` | Sí | El comando no aplica y lo explica claramente. |
| `cancelled` | No | Ejecución interrumpida. |

### 4.4 Criterios de aceptación

- Todos los comandos públicos están clasificados como `stable`, `preview` o `internal`.
- No hay comando stable sin contrato JSON.
- No hay estado final ambiguo.
- El harness de aceptación referencia estos contratos.

---

## 5. Fase 1 — Acceptance harness externo primero

### 5.1 Objetivo

Construir una suite black-box pequeña que pruebe OpenContext como lo usaría un usuario o agente real.

Esta fase debe ir antes de seguir arreglando funcionalidades. Si no, se vuelve a caer en iteraciones subjetivas.

### 5.2 Estructura recomendada

```text
tests/acceptance/
├── README.md
├── conftest.py
├── fixtures/
│   ├── py_bugfix_basic/
│   ├── py_bugfix_no_tests/
│   ├── py_bugfix_wrong_executor/
│   ├── py_large_context/
│   ├── sdd_feature_basic/
│   └── memory_reuse_basic/
├── helpers/
│   ├── cli.py
│   ├── fs.py
│   ├── json_assertions.py
│   ├── workspace.py
│   └── package_install.py
└── test_acceptance_*.py
```

### 5.3 Cómo debe ejecutarse

Debe poder correr de dos maneras:

```bash
# Contra checkout local
pytest tests/acceptance -q --oc-bin ./dist/opencontext.pyz

# Contra paquete instalado como usuario real
python -m venv /tmp/oc-acceptance-venv
/tmp/oc-acceptance-venv/bin/pip install opencontext-cli==X.Y.Z
pytest tests/acceptance -q --oc-bin /tmp/oc-acceptance-venv/bin/opencontext
```

### 5.4 Escenarios mínimos

La suite inicial debe tener aproximadamente 25–35 tests de aceptación. No más.

| ID | Escenario | Prioridad |
|---|---|---:|
| AC-001 | `opencontext version --json` devuelve versión real y JSON limpio. | P0 |
| AC-002 | `opencontext doctor --json` es parseable y no mezcla texto humano. | P0 |
| AC-003 | `workspace init/install` crea archivos esperados. | P0 |
| AC-004 | `workspace status --json` detecta workspace válido. | P0 |
| AC-005 | `index --json` genera índice y KG mínimo. | P0 |
| AC-006 | `knowledge-graph search` encuentra símbolo y test relacionado. | P0 |
| AC-007 | `pack --json` incluye archivos relevantes y excluye irrelevantes. | P0 |
| AC-008 | `pack` reporta presupuesto de tokens y uso de KG. | P0 |
| AC-009 | `run` sin executor devuelve `needs_executor`, no `passed`. | P0 |
| AC-010 | `run` con executor correcto muta archivo y pasa verificación. | P0 |
| AC-011 | `run` con executor incorrecto devuelve `failed` y exit code no cero. | P0 |
| AC-012 | TDD strict falla si no hay test RED. | P0 |
| AC-013 | TDD strict pasa solo con RED → GREEN demostrado. | P0 |
| AC-014 | SDD `new` crea ciclo y artefactos iniciales. | P0 |
| AC-015 | SDD `propose/spec/design/tasks` consume y produce artefactos conectados. | P0 |
| AC-016 | SDD `apply/verify` ejecuta gates reales. | P0 |
| AC-017 | `memory save/search/get` funciona. | P1 |
| AC-018 | Una segunda ejecución recupera memoria aprobada y la reporta como usada. | P0 |
| AC-019 | `memory compact` reduce entradas antiguas sin borrar memoria protegida. | P1 |
| AC-020 | KG incremental actualiza nodos tras cambio de archivo. | P1 |
| AC-021 | Pack bajo presión de tokens aplica compresión y conserva spans protegidos. | P0 |
| AC-022 | `uninstall workspace --purge --verify` elimina residuos gestionados de workspace. | P0 |
| AC-023 | `uninstall product --purge --verify` usa manifest y limpia instalación gestionada. | P0 |
| AC-024 | Errores comunes son accionables y devuelven estructura JSON estable. | P1 |
| AC-025 | Report bundle contiene run manifest, comandos, diffs, verificación, memory delta y graph delta. | P0 |
| AC-026 | `resume` continúa una ejecución interrumpida sin duplicar artefactos. | P1 |
| AC-027 | Policy bloquea comandos peligrosos por defecto. | P0 |
| AC-028 | Secret redaction elimina tokens/secrets de reportes y memoria. | P0 |
| AC-029 | Release artifact no contiene `.git`, `.venv`, caches ni estado local. | P0 |
| AC-030 | Acceptance harness pasa contra paquete instalado limpio. | P0 |

### 5.5 Criterio de aceptación de la fase

- Acceptance harness corre en menos de 3–5 minutos.
- Puede ejecutarse contra binario local y contra paquete instalado.
- Cada test valida comportamiento visible, no internals.
- Cada fallo explica qué contrato se rompió.

---

## 6. Fase 2 — CLI honesto, JSON limpio y exit codes fiables

### 6.1 Objetivo

Convertir la CLI en una API estable para humanos y agentes.

### 6.2 Cambios técnicos

Crear un módulo central:

```text
opencontext_cli/contracts/
├── output.py
├── errors.py
├── exit_codes.py
├── json_schema.py
└── command_registry.py
```

Todos los comandos deben usar este módulo. Queda prohibido que cada comando invente su propia salida.

### 6.3 Flags globales obligatorias

```bash
--json
--quiet
--verbose
--dry-run
--root <path>
--config <path>
--no-color
```

No todos los comandos tienen que soportar todas las flags si no aplican, pero las comunes deben ser uniformes.

### 6.4 Error JSON estándar

```json
{
  "ok": false,
  "status": "failed",
  "error": {
    "code": "TDD_RED_NOT_PROVEN",
    "message": "TDD strict requires a failing test before mutation.",
    "hint": "Add or modify a relevant test, run it, and ensure it fails before applying the fix.",
    "details": {
      "workflow": "oc-flow",
      "phase": "apply"
    }
  }
}
```

### 6.5 Exit codes

| Código | Uso |
|---:|---|
| 0 | Éxito real. |
| 1 | Error genérico o verificación fallida. |
| 2 | Uso incorrecto de CLI. |
| 3 | Configuración inválida. |
| 4 | Policy/security blocked. |
| 5 | Executor/modelo requerido. |
| 6 | TDD strict violado. |
| 7 | Artefactos SDD faltantes/inconsistentes. |
| 8 | Verificación/test fallida. |
| 9 | Instalación/desinstalación incompleta. |

### 6.6 Criterios de aceptación

- Si `--json`, stdout contiene solo JSON.
- Texto humano va a stderr o se suprime con `--quiet`.
- `passed` solo devuelve exit 0 si hay evidencias obligatorias.
- `failed`, `blocked`, `needs_context`, violaciones TDD y verificación fallida devuelven exit no cero.
- Los tests AC-001, AC-002, AC-009, AC-011 y AC-024 pasan.

---

## 7. Fase 3 — Modelo de instalación y desinstalación real

### 7.1 Objetivo

Separar definitivamente:

```text
instalar el producto
preparar un workspace
configurar agentes/integraciones
```

### 7.2 Comandos objetivo

```bash
opencontext product install
opencontext product status
opencontext product uninstall --purge --verify

opencontext workspace init
opencontext workspace status
opencontext workspace uninstall --purge --verify

opencontext agents install
opencontext agents status
opencontext agents uninstall --purge --verify
```

Si se mantiene compatibilidad con comandos antiguos, deben ser aliases documentados.

### 7.3 Manifest global

Cada instalación del producto debe escribir un manifest:

```json
{
  "schema_version": 1,
  "product_version": "1.6.0",
  "install_method": "pipx|pip|venv|installer|manual",
  "created_paths": [],
  "modified_files": [],
  "shell_profile_blocks": [],
  "symlinks": [],
  "env_vars": [],
  "agent_configs": [],
  "timestamp": "2026-07-06T00:00:00Z"
}
```

### 7.4 Manifest workspace

```json
{
  "schema_version": 1,
  "workspace_root": "/repo",
  "created_paths": [
    ".opencontext",
    "opencontext.yaml"
  ],
  "state_paths": [],
  "memory_paths": [],
  "kg_paths": [],
  "backup_paths": []
}
```

### 7.5 Desinstalación

`uninstall --purge --verify` debe:

1. leer manifest;
2. listar lo que va a borrar en `--dry-run`;
3. borrar rutas gestionadas;
4. revertir bloques de shell profile si los creó;
5. eliminar symlinks gestionados;
6. eliminar configs/caches/state gestionados;
7. verificar residuos;
8. reportar cualquier residuo no eliminable.

### 7.6 Criterios de aceptación

- AC-022 y AC-023 pasan.
- El uninstall nunca borra rutas no registradas salvo confirmación explícita.
- El uninstall reporta residuos no gestionados, pero no los elimina silenciosamente.
- `--verify` devuelve fallo si quedan residuos gestionados.

---

## 8. Fase 4 — Harness como núcleo real del runtime

### 8.1 Objetivo

El harness debe dejar de ser una capa opcional y convertirse en el núcleo que da verdad operacional.

### 8.2 Modelo de ejecución

```text
task intake
→ context build
→ plan
→ gates pre-apply
→ mutation
→ gates post-apply
→ verification
→ memory harvest
→ KG update
→ compression metrics
→ report
→ archive/resume metadata
```

### 8.3 Run manifest obligatorio

Cada run crea:

```text
.opencontext/runs/<run_id>/
├── run.json
├── input.json
├── context_pack.md
├── context_pack.json
├── plan.json
├── gates.json
├── mutations.diff
├── verification.json
├── memory_delta.json
├── graph_delta.json
├── metrics.json
├── events.ndjson
└── report.md
```

### 8.4 `run.json` mínimo

```json
{
  "run_id": "...",
  "workflow": "oc-flow|sdd|apply-only",
  "status": "passed|failed|blocked|needs_executor",
  "started_at": "...",
  "finished_at": "...",
  "task": "...",
  "workspace": "...",
  "changed_files": [],
  "verification": {
    "executed": true,
    "commands": [],
    "passed": true
  },
  "tdd": {
    "mode": "off|warn|strict",
    "red_proven": true,
    "green_proven": true
  },
  "context": {
    "kg_used": true,
    "memory_used": true,
    "compression_used": true
  }
}
```

### 8.5 Gates

Gates comunes:

```text
config_valid
workspace_valid
provider_policy_passed
context_pack_created
kg_available_or_explained
memory_available_or_explained
approval_granted_if_required
tdd_red_proven_if_strict
mutation_performed_if_required
verification_executed_if_required
verification_passed_if_required
memory_delta_valid
graph_delta_valid
report_written
```

### 8.6 Criterios de aceptación

- Ningún workflow puede terminar `passed` si falla una gate obligatoria.
- El harness devuelve salida machine-readable estable.
- `report.md` y `run.json` siempre cuentan la misma historia.
- AC-010, AC-011, AC-025 y AC-026 pasan.

---

## 9. Fase 5 — TDD strict real

### 9.1 Objetivo

TDD strict debe ser una garantía real, no una configuración.

### 9.2 Contrato RED → GREEN

Para cualquier tarea de implementación con `tdd.mode = strict`:

1. debe existir un test nuevo o modificado relevante;
2. debe ejecutarse antes de la mutación;
3. debe fallar por el motivo esperado;
4. debe aplicarse la mutación;
5. debe ejecutarse después;
6. debe pasar;
7. la suite de regresión mínima debe pasar;
8. el reporte debe incluir evidencia RED y GREEN.

### 9.3 Evidencia RED

```json
{
  "red": {
    "command": "pytest tests/test_app.py::test_add -q",
    "exit_code": 1,
    "failed_tests": ["tests/test_app.py::test_add"],
    "failure_summary": "assert 0 == 3",
    "captured_at": "..."
  }
}
```

### 9.4 Evidencia GREEN

```json
{
  "green": {
    "command": "pytest -q",
    "exit_code": 0,
    "passed_tests": 1,
    "failed_tests": 0,
    "captured_at": "..."
  }
}
```

### 9.5 Políticas importantes

- Si la tarea es documental o de configuración sin tests aplicables, TDD strict debe devolver `not_applicable` con justificación, no fingir RED/GREEN.
- Si el executor edita solo tests para hacerlos pasar, debe detectarse como sospechoso si no hubo cambio funcional cuando era requerido.
- Si no hay test runner detectable, el flujo debe ser `blocked` o `needs_verification_config`.
- Si los tests ya pasaban antes, no hay RED. En strict, eso falla salvo que el tipo de tarea sea refactor/documentación.

### 9.6 Criterios de aceptación

- AC-012 y AC-013 pasan.
- TDD strict no puede terminar `passed` sin `red_proven=true` y `green_proven=true`.
- Un bug introducido deliberadamente en el detector RED rompe la acceptance suite.

---

## 10. Fase 6 — OC Flow cerrado de extremo a extremo

### 10.1 Objetivo

OC Flow debe ser el flujo rápido y confiable para tareas pequeñas/medianas.

### 10.2 Fases

```text
init
classify_task
gather_context
build_pack
plan
preflight_gates
mutate
inspect_diff
verify
repair_loop
memory_harvest
kg_update
report
archive
```

### 10.3 Estados esperados

- `needs_executor`: si requiere mutación y no hay executor productivo.
- `passed`: si mutó/verificó/generó evidencia.
- `failed`: si hubo executor pero la verificación falló.
- `blocked`: si falta config, test runner o workspace válido.
- `needs_approval`: si policy exige aprobación.

### 10.4 Repair loop

Debe estar limitado:

```yaml
repair:
  max_attempts: 2
  allowed_when:
    - verification_failed
    - lint_failed
  forbidden_when:
    - policy_blocked
    - tdd_red_not_proven
    - missing_executor
```

### 10.5 Criterios de aceptación

- AC-009, AC-010 y AC-011 pasan.
- Un executor incorrecto no puede acabar `passed`.
- El diff aplicado queda en `mutations.diff`.
- La verificación queda en `verification.json`.

---

## 11. Fase 7 — SDD conectado de verdad

### 11.1 Objetivo

SDD debe ser un ciclo funcional con artefactos conectados, no comandos sueltos.

### 11.2 Ciclo

```text
sdd new
→ sdd explore
→ sdd propose
→ sdd spec
→ sdd design
→ sdd tasks
→ sdd apply
→ sdd verify
→ sdd archive
```

### 11.3 Estructura de ciclo

```text
.opencontext/sdd/<cycle_id>/
├── cycle.json
├── explore.md
├── proposal.md
├── spec.md
├── design.md
├── tasks.md
├── apply_runs/
├── verification.json
└── archive.md
```

### 11.4 Reglas

- Cada fase consume el artefacto anterior.
- Cada fase actualiza `cycle.json`.
- No se puede ejecutar `design` sin `spec` válido.
- No se puede ejecutar `apply` sin `tasks` válidas.
- No se puede ejecutar `verify` si no hubo apply o si se declara verify-only explícito.
- En modo TDD strict, `apply` usa el contrato RED → GREEN.

### 11.5 Criterios de aceptación

- AC-014, AC-015 y AC-016 pasan.
- Ninguna fase stable imprime placeholder.
- Si falta un artefacto, devuelve error estructurado con acción correctiva.

---

## 12. Fase 8 — Knowledge Graph como motor real de contexto

### 12.1 Objetivo

El KG debe servir para ahorrar tokens y mejorar decisiones, no solo para buscar símbolos.

### 12.2 Nodos mínimos

```text
file
symbol
test
module
command
config
memory
run
sdd_artifact
decision
risk
```

### 12.3 Aristas mínimas

```text
defines
calls
imports
tests
covers
modified_by
mentioned_by
depends_on
configured_by
related_to_memory
produced_by_run
```

### 12.4 Queries obligatorias

```bash
opencontext kg search <query> --json
opencontext kg impact <file-or-symbol> --json
opencontext kg related-tests <file-or-symbol> --json
opencontext kg explain-pack --run <run_id> --json
```

### 12.5 Indexado incremental

Debe detectar:

- archivos nuevos;
- archivos borrados;
- símbolos modificados;
- tests relacionados;
- aristas obsoletas;
- memoria vinculada a nodos.

### 12.6 Criterios de aceptación

- AC-005, AC-006 y AC-020 pasan.
- KG debe demostrar al menos una relación símbolo → test en fixture básica.
- Después de modificar un archivo, el grafo se actualiza sin reindexar todo salvo que sea necesario.

---

## 13. Fase 9 — Context pack y compresión con ahorro medible de tokens

### 13.1 Objetivo

El context engine debe construir packs útiles, pequeños y verificables.

### 13.2 Pipeline

```text
task understanding
→ workspace scan
→ KG candidate expansion
→ memory recall
→ test discovery
→ ranking
→ budget allocation
→ protected span detection
→ compression
→ pack generation
→ metrics
```

### 13.3 Ranking

Factores recomendados:

| Factor | Peso inicial |
|---|---:|
| Coincidencia directa con tarea | 0.30 |
| Vecindad en KG | 0.25 |
| Tests relacionados | 0.15 |
| Recencia/cambios recientes | 0.10 |
| Memoria vinculada | 0.10 |
| Centralidad/impacto | 0.05 |
| Penalización por tamaño | -0.05 |

### 13.4 Spans protegidos

Nunca comprimir agresivamente:

- firmas de funciones;
- imports;
- assertions de tests;
- interfaces públicas;
- configuración relevante;
- errores y stack traces;
- fragmentos mencionados por memoria o KG;
- cambios recientes.

### 13.5 Métricas obligatorias

```json
{
  "context": {
    "input_tokens_estimated": 18000,
    "output_tokens_estimated": 6200,
    "compression_ratio": 0.34,
    "kg_nodes_used": 12,
    "kg_edges_used": 18,
    "memory_hits": 3,
    "protected_spans": 9,
    "protected_spans_kept": 9,
    "excluded_files": 42
  }
}
```

### 13.6 Criterios de aceptación

- AC-007, AC-008 y AC-021 pasan.
- En fixture grande, el pack debe incluir el archivo funcional y test relevante.
- En fixture grande, debe excluir archivos irrelevantes.
- Bajo presupuesto bajo, debe aplicar compresión y conservar spans protegidos.

---

## 14. Fase 10 — Memoria agéntica real

### 14.1 Objetivo

La memoria debe mejorar ejecuciones posteriores y ahorrar tokens.

### 14.2 Tipos de memoria

```text
fact
decision
preference
constraint
pattern
failure
solution
project_context
```

### 14.3 Estados

```text
proposed
approved
rejected
expired
compacted
purged
```

### 14.4 Flujo

```text
harvest after run
→ propose memory delta
→ classify
→ deduplicate
→ require approval when configured
→ save
→ retrieve in future pack
→ report usage
→ compact/expire
→ purge on uninstall
```

### 14.5 Reglas

- No guardar secretos.
- No guardar raw prompts si `store_raw=false`.
- No usar memoria no aprobada salvo configuración explícita.
- Cada memory hit usado en un run debe quedar en `run.json`.
- Si la memoria influye en una decisión, debe poder explicarse.

### 14.6 Criterios de aceptación

- AC-017, AC-018 y AC-019 pasan.
- Una memoria creada en run 1 debe aparecer como `memory_hit` en run 2.
- El pack debe mostrar qué memoria usó y por qué.
- Uninstall purge elimina memoria gestionada.

---

## 15. Fase 11 — Agentes, executors y policies

### 15.1 Objetivo

Permitir ejecución agéntica segura sin fingir capacidades.

### 15.2 Tipos de executor

```text
none
test_stub
local_patch
external_agent
mcp_sampler
llm_provider
```

### 15.3 Contrato

Cada executor declara:

```json
{
  "id": "test_stub",
  "can_mutate": true,
  "can_run_commands": false,
  "requires_network": false,
  "requires_approval": false,
  "supported_tasks": ["bugfix_basic"]
}
```

### 15.4 Tool policies

Políticas mínimas:

- bloquear comandos destructivos por defecto;
- bloquear acceso a secretos;
- requerir aprobación para escritura fuera del workspace;
- requerir aprobación para red/network si está deshabilitada;
- registrar todos los comandos ejecutados;
- redacción de secretos en reportes.

### 15.5 Criterios de aceptación

- AC-027 y AC-028 pasan.
- Si no hay executor productivo, el sistema devuelve `needs_executor`.
- Si la policy bloquea, no hay mutación parcial.

---

## 16. Fase 12 — UX y DX finales

### 16.1 Objetivo

Que el producto sea usable y comprensible cuando algo falla.

### 16.2 First-run ideal

```bash
opencontext product status
opencontext workspace init
opencontext doctor
opencontext run "fix failing tests" --executor test_stub
```

Debe explicar:

- qué se ha creado;
- qué falta;
- qué comando ejecutar después;
- cómo borrar todo.

### 16.3 Mensajes de error

Mal:

```text
Artifact not found
```

Bien:

```text
No se ha encontrado spec.md para el ciclo SDD actual.
Ejecuta: opencontext sdd spec --cycle <id>
O revisa: .opencontext/sdd/<id>/cycle.json
```

### 16.4 Criterios de aceptación

- Los errores P0 tienen hints accionables.
- `doctor` agrupa problemas por producto/workspace/agentes/memoria/KG.
- `--help` no muestra comandos placeholder como stable.

---

## 17. Fase 13 — Release profesional

### 17.1 Objetivo

Publicar solo si el paquete instalado pasa acceptance.

### 17.2 Release gate

Pipeline:

```text
clean checkout
→ build package
→ inspect artifact hygiene
→ install in fresh venv
→ run smoke acceptance
→ run full acceptance
→ uninstall verify
→ generate release report
→ publish
```

### 17.3 Artifact hygiene

Prohibido publicar:

```text
.git/
.venv/
venv/
.ci-venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
__pycache__/
.opencontext/
.coverage
*.egg-info local accidental
local logs
local state
```

### 17.4 Criterios de aceptación

- AC-029 y AC-030 pasan.
- Release report contiene versión, checksum, acceptance summary y known limitations.
- No hay comandos stable rotos en release.

---

# PARTE II — ESTRATEGIA DE TESTS REALES Y MÁS LIGEROS

---

## 18. Problema con “demasiados tests”

El problema no es el número absoluto de tests. El problema es tener tests con baja señal.

Tests problemáticos:

- prueban detalles internos que cambian todo el tiempo;
- duplican el mismo comportamiento en varias capas;
- validan mocks en vez de comportamiento real;
- están atados a un desarrollo concreto y no al contrato del producto;
- hacen snapshot de estructuras internas inestables;
- fuerzan arquitectura accidental;
- tardan mucho y no detectan errores reales;
- hacen que refactorizar sea caro sin aumentar confianza.

OpenContext debe moverse a una pirámide más simple:

```text
black-box acceptance: pocos, críticos, altísima señal
contract/golden tests: formatos JSON y CLI estables
unit tests: solo algoritmos puros y críticos
integration tests: solo fronteras reales del producto
```

---

## 19. Nueva taxonomía de tests

### 19.1 Nivel A — Acceptance black-box

Prueban el producto desde fuera.

Características:

- ejecutan el binario real;
- usan fixtures pequeñas;
- validan filesystem, JSON, exit codes y artefactos;
- no importan módulos internos;
- representan flujos de usuario/agente.

Cantidad recomendada: **25–35 tests**.

Estos son los tests más importantes del producto.

### 19.2 Nivel B — Golden contract tests

Prueban que salidas públicas no cambian accidentalmente.

Ejemplos:

```text
version --json
status --json
run failed JSON
run passed JSON
memory search JSON
kg search JSON
sdd cycle JSON
```

No deben hacer snapshot gigante. Deben validar schema y campos críticos.

Cantidad recomendada: **15–25 tests**.

### 19.3 Nivel C — Unit tests de algoritmos puros

Solo donde hay lógica crítica y estable:

- ranking de context pack;
- selección de spans protegidos;
- compresión segura;
- deduplicación de memoria;
- scoring de memoria;
- merge/update incremental del KG;
- detector RED/GREEN;
- parsing de manifests;
- redacción de secretos;
- cálculo de exit code desde run state.

Cantidad recomendada: **60–120 tests**, pequeños y rápidos.

### 19.4 Nivel D — Integration tests estrechos

Solo para fronteras reales:

- filesystem state store;
- SQLite/JSON KG store;
- memory repository;
- install manifest writer/reader;
- test runner adapter;
- package artifact inspector.

Cantidad recomendada: **20–40 tests**.

### 19.5 Nivel E — Regression tests puntuales

Solo para bugs reales P0/P1 que ya ocurrieron.

Ejemplos:

- `version --json` no puede volver a `0.0.0`;
- `passed` no puede devolverse si verification failed;
- `sdd apply` no puede decir que faltan artefactos recién creados;
- `memory v2` no puede faltar en paquete;
- `--json` no puede mezclar texto humano.

Cantidad recomendada: **los necesarios**, pero cada uno debe tener ID de bug/regresión.

---

## 20. Tests que deben eliminarse o evitarse

Eliminar o no crear tests de este tipo:

| Tipo | Motivo |
|---|---|
| Tests que validan nombres privados de clases | Rompen refactors sin proteger producto. |
| Tests duplicados de la misma salida en unit + integration + acceptance | Mucho coste, poca señal. |
| Tests con mocks que solo verifican que se llamó a otro mock | No prueban comportamiento. |
| Tests sobre artefactos temporales de una iteración concreta | Se vuelven deuda inmediata. |
| Snapshots enormes de JSON completo | Frágiles; mejor schema + campos críticos. |
| Tests de “implementation path” sin escenario usuario/agente | No ayudan a saber si el producto funciona. |
| Tests que requieren estado local del desarrollador | No reproducibles. |
| Tests que pasan aunque no haya assertions relevantes | Falsa confianza. |

---

## 21. Suite mínima recomendada

### 21.1 Distribución objetivo

| Suite | Cantidad aproximada | Tiempo objetivo |
|---|---:|---:|
| Acceptance smoke | 8–12 | < 60 s |
| Acceptance full | 25–35 | < 5 min |
| Golden contracts | 15–25 | < 30 s |
| Unit core algorithms | 60–120 | < 10 s |
| Integration narrow | 20–40 | < 60 s |
| Regression P0/P1 | variable | < 60 s |

Total razonable inicial: **120–220 tests**, no miles.

El número exacto no importa. La señal sí.

### 21.2 Smoke suite obligatoria

Esta suite debe correr en cada PR:

```text
SMOKE-001 version JSON limpio
SMOKE-002 doctor parseable
SMOKE-003 workspace init/status
SMOKE-004 index + kg search
SMOKE-005 pack incluye símbolo/test
SMOKE-006 run needs_executor sin executor
SMOKE-007 run con test_stub correcto pasa
SMOKE-008 run con test_stub incorrecto falla
SMOKE-009 tdd strict sin RED falla
SMOKE-010 uninstall workspace purge verify
```

### 21.3 Full acceptance suite

Corre en main/release:

- todos los AC-001 a AC-030;
- release install desde paquete construido;
- uninstall product con manifest;
- memoria reutilizada en segunda ejecución;
- compresión bajo presión;
- SDD ciclo completo.

---

## 22. Estilo de tests tipo Gentle AI

El estilo buscado no es “testearlo todo”. Es testear lo que demuestra el producto.

### 22.1 Principios

1. **Fixtures pequeñas, reales y legibles.**
2. **CLI como frontera principal.**
3. **Pocos escenarios, pero completos.**
4. **Assertions sobre comportamiento observable.**
5. **Errores esperados también se prueban.**
6. **Nada depende del ordenador del desarrollador.**
7. **Cada test explica qué protege.**
8. **No hay tests de arquitectura artificial salvo límites críticos.**

### 22.2 Ejemplo de test bueno

```python

def test_oc_flow_with_correct_executor_mutates_and_verifies(oc_bin, tmp_workspace):
    copy_fixture("py_bugfix_basic", tmp_workspace)

    run(oc_bin, "workspace", "init", "--root", tmp_workspace, "--json")

    result = run_json(
        oc_bin,
        "run",
        "fix add function",
        "--root", tmp_workspace,
        "--executor", "test_stub",
        "--json",
    )

    assert result["status"] == "passed"
    assert result["mutation"]["changed_files"] == ["app.py"]
    assert result["verification"]["passed"] is True
    assert result["tdd"]["green_proven"] is True
    assert_file_contains(tmp_workspace / "app.py", "return a + b")
```

### 22.3 Ejemplo de test malo

```python

def test_runner_calls_internal_phase_method(mocker):
    phase = mocker.patch("opencontext.workflow.Phase.run")
    runner = Runner(...)
    runner.execute()
    phase.assert_called_once()
```

Ese test no demuestra que el producto funcione. Solo congela una implementación.

---

## 23. Contratos que sí merecen unit tests

### 23.1 Context ranking

Casos:

- archivo con símbolo exacto gana a archivo sin símbolo;
- test relacionado sube en ranking;
- archivo enorme irrelevante baja;
- memoria vinculada sube;
- vecinos KG relevantes se incluyen;
- presupuesto bajo excluye candidatos menos relevantes.

### 23.2 Compresión

Casos:

- conserva imports;
- conserva firma;
- conserva assertions;
- conserva spans marcados por KG;
- reduce cuerpo irrelevante;
- reporta ratio;
- falla si eliminaría spans protegidos obligatorios.

### 23.3 Memory

Casos:

- dedupe por contenido semántico/hash;
- scoring por recencia y relevancia;
- approved vs proposed;
- expiry;
- secret redaction;
- compaction conserva decisiones importantes.

### 23.4 KG

Casos:

- parsea símbolos;
- crea `file -> defines -> symbol`;
- crea `test -> tests -> symbol` cuando detecta relación;
- elimina nodos obsoletos;
- update incremental no duplica aristas;
- impact query devuelve vecinos esperados.

### 23.5 TDD detector

Casos:

- RED válido;
- test ya pasaba, no RED;
- fallo de sintaxis no cuenta como RED válido salvo configuración;
- GREEN válido;
- GREEN sin mutación requerida no pasa;
- cambio solo en test sospechoso cuando se esperaba cambio funcional.

### 23.6 Manifests

Casos:

- install manifest válido;
- path fuera de scope bloqueado;
- dry-run no borra;
- verify detecta residuo gestionado;
- uninstall no borra rutas no registradas.

---

## 24. Tests de aceptación concretos por flujo

### 24.1 Flujo 1 — Primer uso

```text
GIVEN paquete instalado limpio
WHEN usuario ejecuta product status, workspace init, doctor
THEN obtiene estado claro, workspace válido y siguientes pasos accionables
```

Protege:

- instalación;
- CLI;
- JSON;
- workspace manifest;
- doctor.

### 24.2 Flujo 2 — Bugfix agéntico con TDD

```text
GIVEN proyecto Python con bug y test fallando
WHEN opencontext run "fix add" --executor test_stub --tdd strict
THEN demuestra RED, muta app.py, demuestra GREEN, actualiza KG, propone memoria y genera reporte
```

Protege:

- OC Flow;
- TDD strict;
- executor;
- verification;
- KG;
- memory delta;
- report.

### 24.3 Flujo 3 — Falta executor

```text
GIVEN tarea que requiere mutación
WHEN opencontext run sin executor productivo
THEN devuelve needs_executor, no muta nada y explica cómo continuar
```

Protege:

- honestidad;
- no false-positive;
- UX.

### 24.4 Flujo 4 — Executor incorrecto

```text
GIVEN proyecto con bug
WHEN executor aplica cambio incorrecto
THEN verificación falla, exit code != 0 y estado failed
```

Protege:

- exit codes;
- verification;
- repair/failure.

### 24.5 Flujo 5 — SDD completo

```text
GIVEN workspace válido
WHEN usuario ejecuta sdd new/propose/spec/design/tasks/apply/verify
THEN cada fase consume el artefacto anterior y produce el siguiente
```

Protege:

- lifecycle SDD;
- artefactos;
- estado de ciclo.

### 24.6 Flujo 6 — Memoria reutilizada

```text
GIVEN run 1 aprende una convención del proyecto y se aprueba la memoria
WHEN run 2 pide una tarea relacionada
THEN el pack incluye esa memoria y el reporte declara que fue usada
```

Protege:

- memoria real;
- recall;
- ahorro de contexto;
- auditabilidad.

### 24.7 Flujo 7 — KG/context/compression

```text
GIVEN fixture con muchos archivos y presupuesto bajo
WHEN pack se genera para una tarea concreta
THEN incluye símbolo y test relevantes, excluye ruido, comprime y conserva spans protegidos
```

Protege:

- KG;
- ranking;
- compresión;
- token savings.

### 24.8 Flujo 8 — Uninstall sin residuos

```text
GIVEN producto/workspace instalado con manifest
WHEN uninstall --purge --verify
THEN no quedan residuos gestionados y los no gestionados se reportan sin borrarse
```

Protege:

- ciclo de vida;
- seguridad;
- confianza del usuario.

---

## 25. Qué mantener como tests internos

Mantener solo tests internos que protejan lógica difícil o peligrosa:

```text
context ranking
compression protected spans
memory dedupe/scoring/redaction
KG incremental update
TDD RED/GREEN classification
manifest uninstall safety
exit code mapping
JSON schema generation
policy blocking
```

No mantener tests internos para:

```text
orden exacto de llamadas internas
nombres privados de fases
estructura temporal de objetos internos
mocks sin efecto real
snapshots enormes
implementaciones experimentales preview
```

---

## 26. Plan de reducción de tests existentes

### 26.1 Paso 1 — Inventario

Crear reporte:

```bash
python scripts/test_inventory.py
```

Debe listar:

```text
test path
suite
runtime
qué contrato protege
si es unit/integration/acceptance/regression
si tiene ID de requisito/bug
si usa mocks
si toca filesystem
si es flaky
```

### 26.2 Paso 2 — Clasificación

Cada test se etiqueta:

```text
KEEP_ACCEPTANCE
KEEP_CONTRACT
KEEP_UNIT_CRITICAL
KEEP_INTEGRATION_BOUNDARY
KEEP_REGRESSION
MERGE
DELETE
QUARANTINE
```

### 26.3 Paso 3 — Eliminación segura

Regla:

- Si un test interno está cubierto por acceptance, se elimina salvo que proteja algoritmo crítico.
- Si dos tests prueban lo mismo, se deja el más externo o el más claro.
- Si un test solo prueba mocks, se elimina.
- Si un test es flaky, se arregla o se pone en quarantine con fecha de caducidad.

### 26.4 Paso 4 — Coverage por contratos, no por líneas

La métrica principal no debe ser cobertura de líneas. Debe ser cobertura de contratos.

```text
P0 contracts covered: 100%
P1 contracts covered: >= 80%
P2 contracts covered: best effort
```

---

# PARTE III — ROADMAP ORDENADO

---

## 27. Orden exacto recomendado

### Sprint 0 — Freeze y contratos

Duración sugerida: 1–2 días.

Entregables:

- `PRODUCT_CONTRACT.md`;
- `CLI_CONTRACT.md`;
- `RUN_STATE_CONTRACT.md`;
- lista de comandos stable/preview/internal;
- tabla de P0 acceptance.

No tocar core salvo para documentar contratos.

### Sprint 1 — Acceptance harness black-box

Duración sugerida: 2–4 días.

Entregables:

- infraestructura `tests/acceptance`;
- fixtures mínimas;
- AC-001 a AC-013;
- smoke suite en CI.

Criterio:

- la suite debe fallar contra el producto actual donde haya bugs conocidos;
- eso es bueno: demuestra que detecta problemas reales.

### Sprint 2 — CLI truth layer

Duración sugerida: 2–4 días.

Entregables:

- output/error/exit code centralizados;
- JSON limpio;
- doctor/status/version normalizados;
- regression tests de JSON y exit codes.

Criterio:

- AC-001, AC-002, AC-009, AC-011, AC-024 pasan.

### Sprint 3 — Harness core y run manifest

Duración sugerida: 4–6 días.

Entregables:

- run manifest;
- gates reales;
- report bundle;
- estados finales cerrados;
- no `passed` sin evidence.

Criterio:

- AC-010, AC-011, AC-025 pasan.

### Sprint 4 — TDD strict real

Duración sugerida: 3–5 días.

Entregables:

- detector RED;
- detector GREEN;
- evidence model;
- strict mode enforcement;
- falsos positivos bloqueados.

Criterio:

- AC-012 y AC-013 pasan.

### Sprint 5 — OC Flow E2E

Duración sugerida: 3–5 días.

Entregables:

- OC Flow conectado al harness;
- repair loop limitado;
- changed files/diff;
- verification report;
- memory/KG hooks aunque sean mínimos.

Criterio:

- bugfix básico pasa;
- executor incorrecto falla;
- sin executor devuelve needs_executor.

### Sprint 6 — SDD lifecycle

Duración sugerida: 4–7 días.

Entregables:

- ciclo SDD persistente;
- comandos conectados;
- artefactos enlazados;
- apply usa harness;
- verify usa verification real.

Criterio:

- AC-014, AC-015, AC-016 pasan.

### Sprint 7 — KG/context/compression

Duración sugerida: 5–8 días.

Entregables:

- KG incremental mínimo;
- related tests;
- impact;
- pack ranking;
- compression metrics;
- protected spans.

Criterio:

- AC-005, AC-006, AC-007, AC-008, AC-020, AC-021 pasan.

### Sprint 8 — Memory real

Duración sugerida: 4–7 días.

Entregables:

- memory states;
- approval flow;
- reuse in pack;
- compaction;
- purge.

Criterio:

- AC-017, AC-018, AC-019 pasan.

### Sprint 9 — Install/uninstall product/workspace/agents

Duración sugerida: 4–7 días.

Entregables:

- manifest global;
- manifest workspace;
- dry-run;
- purge;
- verify;
- safety rules.

Criterio:

- AC-003, AC-004, AC-022, AC-023 pasan.

### Sprint 10 — Test cleanup y suite final

Duración sugerida: 3–6 días.

Entregables:

- inventario de tests;
- eliminación de tests de baja señal;
- suite smoke/full;
- regression list P0;
- CI matrix simplificada.

Criterio:

- PR suite rápida;
- release suite completa;
- no tests raros atados a implementaciones accidentales.

### Sprint 11 — Release gate

Duración sugerida: 2–4 días.

Entregables:

- clean build;
- artifact hygiene;
- install from package;
- full acceptance;
- uninstall verify;
- release report.

Criterio:

- AC-029, AC-030 pasan.

---

## 28. Definition of Done final

OpenContext está completo cuando:

1. el paquete publicado se instala en entorno limpio;
2. `version`, `doctor`, `status` devuelven JSON limpio;
3. workspace init/status/index/pack funcionan;
4. KG encuentra símbolos, tests e impacto;
5. pack usa KG/memoria y reporta ahorro de tokens;
6. compresión conserva spans protegidos;
7. OC Flow sin executor no finge éxito;
8. OC Flow con executor correcto muta y verifica;
9. OC Flow con executor incorrecto falla;
10. TDD strict exige RED → GREEN real;
11. SDD lifecycle completo funciona;
12. memoria se guarda, aprueba, reutiliza, compacta y purga;
13. harness genera evidencias completas;
14. install/uninstall usan manifest y verifican residuos;
15. release artifact está limpio;
16. acceptance harness pasa contra paquete instalado;
17. los tests son pocos, reales y mantenibles.

---

## 29. Métricas de éxito

### 29.1 Producto

| Métrica | Objetivo |
|---|---:|
| P0 acceptance pass rate | 100% |
| JSON parse failures | 0 |
| False `passed` states | 0 |
| TDD strict false positives | 0 |
| Managed uninstall residue | 0 |
| Release artifact hygiene violations | 0 |

### 29.2 Contexto/tokens

| Métrica | Objetivo inicial |
|---|---:|
| Relevant file inclusion | >= 95% en fixtures |
| Irrelevant file exclusion | >= 80% en fixture grande |
| Protected spans kept | 100% |
| Token reduction under budget | >= 40% en fixture grande |
| Memory hit usefulness | demostrada en AC-018 |

### 29.3 Tests

| Métrica | Objetivo |
|---|---:|
| Smoke suite time | < 60 s |
| Full acceptance time | < 5 min |
| Unit core time | < 10 s |
| Flaky tests | 0 tolerados en P0 |
| Tests sin contrato/bug asociado | 0 en suites P0/P1 |

---

## 30. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Seguir añadiendo features | Alto | Freeze de scope y acceptance primero. |
| Tests vuelven a crecer sin señal | Alto | Taxonomía obligatoria y test inventory. |
| SDD se queda decorativo | Alto | AC-014/015/016 bloquean release. |
| TDD strict sigue con falsos positivos | Alto | RED/GREEN evidence obligatoria. |
| Memoria se queda en CRUD | Medio-alto | AC-018 exige reutilización real. |
| KG no ahorra tokens | Medio-alto | AC-021 mide pack bajo presión. |
| Uninstall borra demasiado | Alto | Manifest y safety rules. |
| Uninstall borra demasiado poco | Medio | Verify residue. |
| CLI rompe agentes por salida humana | Alto | JSON limpio y golden contracts. |

---

## 31. Resumen de prioridades P0

Orden real de P0:

```text
1. Acceptance harness externo
2. JSON/exit codes/estados honestos
3. Harness con evidencias reales
4. TDD strict RED → GREEN
5. OC Flow E2E
6. SDD lifecycle conectado
7. Context/KG/compression bajo presión
8. Memoria reutilizada en segunda ejecución
9. Install/uninstall con manifest y purge verify
10. Release gate desde paquete instalado limpio
```

No cambiaría ese orden.

---

## 32. Conclusión

Este plan cambia el criterio de éxito de OpenContext.

Antes, el progreso podía parecer:

```text
hay comando
hay módulo
hay JSON
hay test
```

A partir de ahora debe ser:

```text
hay contrato
hay acceptance externa
hay evidencia
hay fallo correcto cuando algo no se cumple
hay release gate reproducible
```

La estrategia de tests no debe crecer por miedo. Debe reducirse a pruebas que dan confianza real:

- acceptance black-box para flujos de producto;
- golden contracts para CLI/JSON;
- unit tests solo para algoritmos críticos;
- integration tests solo para fronteras reales;
- regressions solo para bugs reales.

Si se ejecuta el plan en este orden, OpenContext puede dejar de ser un conjunto de piezas prometedoras y convertirse en un sistema agéntico cerrado: harness real, memoria real, compresión medible, grafo útil, ahorro de tokens, TDD verificable, instalación/desinstalación confiable y una UX que no miente.
