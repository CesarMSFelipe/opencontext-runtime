# The TUI menu system

OpenContext ships a single, keyboard-navigable terminal UI. Every interactive
prompt — menus, settings, confirmations, wizards — goes through one engine, wears
the same OpenContext logo, and degrades gracefully when there is no terminal.

This page documents how that system is built and how to extend it. For a
step-by-step visual tour of the screens, see the
[configuration walkthrough](walkthrough.md).

---

## Design rules

The TUI obeys four invariants. They are not style preferences — they are
enforced (see [Guarantees](#guarantees-and-how-they-are-enforced)).

1. **Everything is navigable.** No menu asks you to type a number or a word.
   You move with `↑↓`, toggle with `Space`, confirm with `Enter`. Even yes/no is
   a `Yes`/`No` selector, never a typed `(y/n)`.
2. **One configuration surface.** All settings live in a single menu
   (`run_config_menu`). Both `opencontext` (home → *Settings*) and
   `opencontext config` open that same menu — config is never scattered across
   two places.
3. **No dead ends.** Every menu has `Back`/`Quit` and returns to its caller.
4. **No hangs.** Without a TTY (CI, pipes), prompts return their default instead
   of blocking forever.

---

## The prompt engine — `opencontext_core/prompts.py`

A single module backs every interactive prompt, so the whole product has one
arrow-key UX and one degradation path.

| Function | Returns | UX |
|---|---|---|
| `select(message, choices, *, default, instruction)` | chosen value | single-choice list |
| `checkbox(message, choices, *, defaults, require_one, instruction)` | list of values | multi-select (`Space` to toggle) |
| `confirm(message, *, default)` | `bool` | a `Yes`/`No` **selector** (delegates to `select`) |
| `text(message, *, default, instruction)` | `str` | free-text entry |
| `secret(message)` | `str` | hidden entry (API keys) |
| `pause(message)` | `None` | wait for `Enter` (no-op when not a TTY) |

`choices` accept `"value"`, `("value", "label")`, or `{"value":…, "name":…}`.
A choice whose value is `None` renders as a non-selectable **separator**
(`prompts.SEPARATOR`), used to group menu sections.

### Degradation (in order)

```
1. InquirerPy + a real TTY  → arrow-key selectors / checkboxes   (cursor ❯, ◉/○)
2. A TTY but no InquirerPy   → Rich text prompts (still usable)
3. No TTY (CI, pipes, --yes) → return the default, never prompt   (no hang/crash)
```

`InquirerPy` is the arrow-key backend. It is declared as a dependency of
**both** `opencontext-cli` and `opencontext-core` (the package that imports it),
so a standalone core install still gets arrow keys rather than silently falling
back to the Rich text prompt.

!!! note "If menus render as typed prompts"
    Seeing `Main menu [install/upgrade/…] (install):` means InquirerPy is not
    importable in the environment running `opencontext` (you hit tier 2/3). Fix:
    reinstall so the dependency is present, e.g. `pipx install --force <repo>` or
    `pipx inject opencontext-cli InquirerPy`.

---

## Branding — the logo

The logo (the knowledge-graph `◉──◉` motif) is the single source of truth in
`opencontext_core/dx/console_styles.py`:

- `LOGO` — full 7-line form, shown on the home menu and roomy terminals.
- `COMPACT_LOGO` — 3-line form, shown on action/settings screens and small
  terminals.
- `show_logo(*, compact=False)` — prints the right form for the terminal size.

It lives in **core** (not the CLI) so both the CLI menus and the core wizards can
render the same icon — `opencontext-core` cannot import `opencontext-cli`, but
everything can import core.

Every action screen renders it through one helper, `_action_header(title)` in
`menu_cmd.py`, which clears the screen, prints the compact logo, then the title.
That is why the icon appears on every menu and sub-screen, not just the home
menu.

---

## Menu architecture

```
opencontext            →  run_main_menu()      (home: Setup · Configure · Tools)
                              └─ "Settings"  ─┐
                                              ├─→  run_config_menu()   ← one surface
opencontext config     ───────────────────────┘
opencontext config wizard ─────────────────────┘
```

Both live in `opencontext_cli/commands/menu_cmd.py`. `config_cmd.py` routes
`opencontext config` into `run_config_menu` so there is exactly one config menu.

### Home menu — `run_main_menu`

The launcher. Shows the full logo, a knowledge-graph status header, and an
update banner, then three groups:

- **Setup** — Install / reconfigure · Upgrade · Re-sync
- **Configure** — **Settings** (opens the config menu)
- **Tools** — Verified context · Context memory · Doctor · Backups · Uninstall

### Configuration menu — `run_config_menu`

The single settings surface. Each entry appears once and is reached by one path:

| Entry | Backed by |
|---|---|
| Full setup wizard | `wizard.run_wizard` |
| Security & privacy | `wizard.reconfigure("security")` |
| Features | `wizard.reconfigure("features")` (checkbox) |
| Token budgets | `wizard.reconfigure("tokens")` |
| Providers & models | `_run_configure_models` |
| Agent integrations | `_run_agent_integrations` (checkbox) |
| Plugins | `wizard.reconfigure("plugins")` (checkbox) |
| Memory backend | `_run_memory_backend` → `memory.provider` |
| Language | `_run_language` → `ui_language` |
| SDD & TDD settings | `_run_sdd_profiles` |
| Show current config | `wizard.show_config` |
| Reset to defaults | `wizard.reset_config` |

The menu **loop** lives in the CLI because it composes CLI actions with core
wizard actions; the individual setting actions live in core
(`opencontext_core/wizard.py`) where they can be reused by the
`config reconfigure` subcommand.

Settings that stay CLI-only (authoring or one-shot ops, not interactive config):
`profile create/delete`, `skill create`, `stack --write`, `telemetry clear`,
`sync`, backup/restore (under home → Backups), and provider API-key entry
(security-sensitive, handled by `install`).

---

## Guarantees and how they are enforced

| Guarantee | Mechanism |
|---|---|
| No raw/typed prompts | `tests/cli/test_no_raw_interactive_prompts.py` greps source and fails on `input(`, `Prompt.ask`, `Confirm.ask` |
| No hang without a TTY | every menu loop early-returns when `stdin`/`stdout` are not a TTY; `tests/cli/test_menu_actions.py::test_config_menu_non_tty_does_not_hang` |
| Multi-select where it matters | features, agents, plugins use `checkbox`; `tests/core/test_wizard_multiselect.py` |
| Safe config writes | `config_sync.set_yaml_key` validates the patched YAML loads and reverts on failure |

---

## Extending the TUI

### Add a setting to the config menu

1. Write an action. If it is a CLI-side action (needs CLI helpers), add a
   `_run_*` function in `menu_cmd.py` that starts with `_action_header("Title")`
   (gives it the logo) and uses `prompts.select`/`checkbox`. If it is a core
   setting, add a branch to `wizard.reconfigure` and wrap it in
   `run_config_menu` with `_wrap("Title", …)` so it gets a header.
2. Add a `(key, "Label")` row to the `prompts.select` choices in
   `run_config_menu`, and the `key → action` mapping in its `actions` dict.
3. Persist with `config_sync.set_yaml_key("dotted.path", value)` for runtime
   YAML keys, or `UserConfigStore` for user preferences.
4. Keep it navigable (selectors, not typed input) and make sure it returns to
   the menu.

### Add a top-level menu

Mirror `run_config_menu`: start with the non-TTY guard, loop on a
`prompts.select` whose last entry is `Back`/`Quit`, dispatch through an actions
dict, and call `_action_header` for each sub-screen. Never add a second config
menu — extend the existing one.

### Layering

`opencontext-cli` may import `opencontext-core`; never the reverse. Shared TUI
pieces (the prompt engine, the logo) therefore live in core
(`prompts.py`, `dx/console_styles.py`).

---

## Wizards

Guided, linear flows that share the same engine and logo:

- **Onboarding** (`opencontext_core/onboarding/wizard.py`) — template, security,
  TDD, agents, memory backend.
- **Setup** (`opencontext_cli/commands/setup_cmd.py`) — 6 steps with a plan
  review and a final confirm.
- **Install** (`main.py`) — language, editor, provider key.

Each clears the screen, shows the logo, and ends in a single navigable
confirmation. They are forward-only by design; the escape is the final
`Yes`/`No` confirm (or `Ctrl-C`).

---

## See also

- [Configuration walkthrough](walkthrough.md) — step-by-step screens.
- [User configuration](user-config.md) — the preference store and dotted keys.
- [Configuration reference](reference.md) — every `opencontext.yaml` field.
