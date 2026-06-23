# Configuración de OpenContext — recorrido paso a paso

> **Objetivo de este documento:** demostrar que toda la configuración vive en **un
> solo menú navegable**, no diseminada en varios comandos ni con caminos
> paralelos, sin puntos muertos, y **sin tener que tipear palabras ni `y/n`** como
> respuesta. Todo se elige con flechas.

> **Sobre las "capturas":** un TUI de teclas-flecha necesita una terminal real
> (InquirerPy no se renderiza sin TTY). Los siguientes son **frames reconstruidos
> fielmente desde el código fuente** — cada label, opción y leyenda sale literal
> de los archivos citados. No son fotos; son el render exacto que produce el
> código. Símbolos reales de InquirerPy: cursor `❯`, check `◉`, sin-check `○`.

---

## 0. Un solo menú, dos puertas (no está diseminado)

Antes había **dos** menús de configuración con opciones solapadas. Ahora hay
**uno** (`run_config_menu`, en `menu_cmd.py`) y las dos puertas de entrada
abren exactamente ese mismo menú:

```
opencontext            →  home menu  →  "Settings (Configure)" ┐
                                                                ├─→  run_config_menu()
opencontext config     →  (sin subcomando / wizard)            ┘
```

| Entrada | Va a | Código |
|---|---|---|
| `opencontext` (sin args) → *Settings* | menú de config único | `main.py:1147` → `menu_cmd.run_main_menu` → `run_config_menu` |
| `opencontext config` | el mismo menú | `config_cmd.py:73-78` → `run_config_menu` |
| `opencontext config wizard` | el mismo menú | `config_cmd.py:83-88` → `run_config_menu` |

Cada perilla aparece **una sola vez** y se llega por **un solo camino**.

---

## 1. Home — `opencontext`

`menu_cmd.py:99`. Todo es selector; la sección *Configure* es **una sola
entrada** que abre el menú de config (ya no hay models/agents/plugins/sdd
sueltos compitiendo acá).

```text
? Main menu
    Setup
  ❯ Install / reconfigure
    Upgrade all packages
    Re-sync environment
    Configure
    Settings (providers, agents, plugins, SDD, features…)
    Tools
    Verified context for a task
    Context memory
    Doctor
    Backups
    Uninstall
    Quit
  ↑↓ move · Enter confirm
```

`Setup` / `Configure` / `Tools` son separadores no seleccionables (el cursor los
salta). Elegís **Settings** y entrás al menú único de configuración.

---

## 2. Menú de Configuración (único)

`menu_cmd.py:run_config_menu`. Acá vive **todo** lo configurable. `Back`
devuelve al home — nunca quedás encerrado.

```text
? Configuration
    Setup
  ❯ Full setup wizard
    Settings
    Security & privacy
    Features
    Token budgets
    Providers & models
    Agent integrations
    Plugins
    SDD & TDD settings
    Config file
    Show current config
    Reset to defaults
    Back
  ↑↓ move · Enter confirm
```

---

## 3. Cada perilla, paso a paso

### 3.1 Security & privacy — selector

`wizard.reconfigure("security")`. Cuatro modos, se elige con flechas (no se
escribe el nombre).

```text
? Security mode:
  ❯ developer
    private_project
    enterprise
    air_gapped
  ↑↓ move · Enter confirm
```

### 3.2 Features — checkbox (multiselect)

`wizard.reconfigure("features")` / `wizard.py:192`. Espacio para togglear,
varias a la vez. Pre-marcadas según el estado actual.

```text
? Enable features
  ❯ ◉ Knowledge Graph (code indexing & search)
    ◉ Call Graph (function call analysis)
    ○ Learning System (auto-optimize token usage)
    ○ Governance (audit trails & policies)
    ◉ Embeddings (semantic search)
    ◉ MCP Server (agent integration)
    ○ Git Integration (context from git history)
  ↑↓ move · Space toggle · Enter confirm
```

### 3.3 Token budgets — número

`wizard.reconfigure("tokens")`. Acá sí se tipea un número, porque es una
**cantidad libre**, no una lista para navegar (ver §5).

```text
Default token budget per operation (8000): ▮
```

### 3.4 Providers & models — selector → selector

`menu_cmd._run_configure_models`. Primero provider, después modelo; ambos
selectores. Nada se tipea (salvo que el provider no tenga modelos conocidos).

```text
? Default provider
  ❯ anthropic
    openai
    mock
  ↑↓ move · Enter confirm
```
```text
? Default model
  ❯ claude-sonnet-4-6
    claude-opus-4-8
    claude-haiku-4-5-20251001
  ↑↓ move · Enter confirm
```

### 3.5 Agent integrations — checkbox (multiselect)

`menu_cmd._run_agent_integrations`. Antes era selector de **uno por vez**; ahora
es checkbox: elegís todos los que quieras y los cablea de una. Lista =
`KNOWN_AGENTS` (23 agentes).

```text
? Select agents to configure
  ❯ ◉ claude-code
    ◉ opencode
    ○ cursor
    ○ gemini-cli
    ○ vscode-copilot
    ○ codex
    ○ windsurf
    ○ aider
    … (KNOWN_AGENTS completo)
  ↑↓ move · Space toggle · Enter confirm
```

### 3.6 Plugins — checkbox (multiselect)

`wizard.reconfigure("plugins")` → `_plugin_wizard_step`. Antes era una cadena de
`Install 'x'?` sí/no, uno por plugin. Ahora un solo checkbox.

```text
? Select plugins to install
  ❯ ◉ sdd-orchestrator — Spec-driven development flow
    ○ memory-engram — Persistent agent memory
    ◉ quality-gate — Architecture & code-quality gate
    ○ git-context — Context from git history
  ↑↓ move · Space toggle · Enter confirm
```

### 3.7 SDD & TDD — selector → selector

`menu_cmd._run_sdd_profiles`.

```text
? SDD model profile
  ❯ default
    cheap
    hybrid
    premium
  ↑↓ move · Enter confirm
```
```text
? TDD mode
  ❯ ask
    strict
    off
  ↑↓ move · Enter confirm
```

### 3.8 Full setup wizard — encadena todo lo anterior

`wizard.run_wizard`. Una pasada guiada: Security (3.1) → Features (3.2) → Token
budgets (3.3) → Agents (checkbox) → Plugins (3.6) → Learning (selectores
Yes/No) → confirmación final. Mismos componentes navegables, en secuencia.

### 3.9 Reset — confirmación SIN `y/n`

`wizard.reset_config`. La confirmación **no** es `(y/n)` tipeado: es un selector
Yes/No (`prompts.confirm` → `prompts.select`, `prompts.py:185`).

```text
? Reset ALL configuration to defaults?
  ❯ Yes
    No
  ↑↓ move · Enter confirm
```

---

## 4. Propiedades garantizadas (la prueba)

| Propiedad | Cómo se garantiza | Dónde |
|---|---|---|
| **Un solo menú, no diseminado** | dos entradas abren `run_config_menu`; cada perilla aparece una vez | `menu_cmd.run_config_menu`, `config_cmd.py:73-88` |
| **Sin `y/n` tipeado** | `confirm()` es un selector Yes/No, no `input()` | `prompts.py:185-192` |
| **Todo navegable** | un único motor (`prompts.select/checkbox`) con flechas | `prompts.py` |
| **Navegabilidad blindada en CI** | un test grepea el source y rompe si aparece `input(`, `Prompt.ask`, `Confirm.ask` | `tests/cli/test_no_raw_interactive_prompts.py` |
| **Sin puntos muertos** | todo menú tiene `Back`/`Quit`; los loops vuelven al menú | `run_main_menu`, `run_config_menu` |
| **Sin cuelgue (CI / pipes)** | sin TTY, el menú avisa y sale en vez de loopear infinito | guard al inicio de `run_config_menu`; test `test_config_menu_non_tty_does_not_hang` |
| **Multiselect donde corresponde** | features, agents, plugins son checkbox | §3.2 / §3.5 / §3.6 |

---

## 5. Una sola excepción, honesta

**Token budgets** (§3.3) se tipea como número. No es un menú porque es una
cantidad libre (ej. `8000`), no una lista finita para navegar — `prompts` no
expone un selector numérico. Es el único input tecleado del flujo; todo lo
demás se maneja con flechas. Si se quisiera, se podría ofrecer presets navegables
(`4k / 8k / 16k / custom`), pero hoy es entrada directa a propósito.

---

### Resumen

Una superficie (`run_config_menu`), dos puertas que llevan a ella, cada ajuste
una sola vez, todo con flechas/espacio/Enter, `Back` en todos lados, sin
cuelgues y con un test que impide volver a meter prompts crudos. Eso es lo que
pediste: un menú bien elaborado, no un montón de comandos disgregados.
