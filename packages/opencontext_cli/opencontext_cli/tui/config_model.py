"""The configuration menu model — framework-agnostic data the TUI renders.

A list of ``Category`` → ``Leaf`` settings. Each leaf is either a ``select`` (its
``options``/``current``/``apply`` drive an in-place pick), a ``launch`` (handled by a
native Textual screen when one is registered, else its ``run`` guided handler), or
``quit``. The Textual screens in ``tui.app``/``tui.sub_screens`` consume this; keeping
it data-only means the menu structure has one definition, tested in isolation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Leaf:
    key: str
    label: str
    kind: str = "launch"
    description: str = ""
    run: Callable[[], None] | None = None
    options: Callable[[], list[tuple[str, str]]] | None = None
    current: Callable[[], str] | None = None
    apply: Callable[[str], str] | None = None


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    shortcut: str
    leaves: tuple[Leaf, ...]


def build_config_model() -> list[Category]:
    """Build the configuration categories. Imports are local so this module stays
    cheap to import and the model is testable in isolation."""
    from opencontext_core import wizard
    from opencontext_core.config import SecurityMode

    def _prefs() -> Any:
        from opencontext_core.user_prefs import UserConfigStore

        return UserConfigStore()

    # ── simple in-place selects ──
    def sec_opts() -> list[tuple[str, str]]:
        return [(m.value, m.value) for m in SecurityMode]

    def sec_cur() -> str:
        return _prefs().load().security_mode or ""

    def sec_apply(val: str) -> str:
        store = _prefs()
        p = store.load()
        p.security_mode = val
        store.save(p)
        return f"Security mode → {val}"

    def lang_opts() -> list[tuple[str, str]]:
        return [("en", "English"), ("es", "Español")]

    def lang_cur() -> str:
        from opencontext_core.config import find_config, load_config

        cf = find_config(".")
        if cf and cf.exists():
            try:
                return getattr(load_config(cf), "ui_language", "en") or "en"
            except Exception:
                return "en"
        return "en"

    def lang_apply(val: str) -> str:
        from opencontext_core.config_sync import set_yaml_key

        return f"Language → {val}" if set_yaml_key("ui_language", val) else "No opencontext.yaml"

    def prof_cur() -> str:
        return _prefs().load().sdd.sdd_model_profile or "default"

    def prof_apply(val: str) -> str:
        store = _prefs()
        p = store.load()
        p.sdd.sdd_model_profile = val
        store.save(p)
        return f"SDD profile → {val}"

    def tdd_cur() -> str:
        return _prefs().load().sdd.tdd_mode or "ask"

    def tdd_apply(val: str) -> str:
        store = _prefs()
        p = store.load()
        p.sdd.tdd_mode = val
        store.save(p)
        return f"TDD mode → {val}"

    def opt_list(*vals: str) -> Callable[[], list[tuple[str, str]]]:
        return lambda: [(v, v) for v in vals]

    setup = Category(
        "setup",
        "Setup",
        "1",
        (
            Leaf(
                "wizard",
                "Full setup wizard",
                "launch",
                "Walk every step: security, features, budgets, agents, plugins.",
                run=wizard.run_wizard,
            ),
        ),
    )
    settings = Category(
        "settings",
        "Settings",
        "2",
        (
            Leaf(
                "security",
                "Security & privacy",
                "select",
                "Posture: how much OpenContext is allowed to reach out.",
                options=sec_opts,
                current=sec_cur,
                apply=sec_apply,
            ),
            Leaf(
                "features",
                "Features",
                "launch",
                "Toggle Knowledge Graph, Call Graph, Learning System.",
            ),
            Leaf(
                "tokens",
                "Token budgets",
                "launch",
                "Default per-operation token budget.",
            ),
            Leaf(
                "models",
                "Providers & models",
                "launch",
                "Default provider + model, and per-SDD-phase routing.",
            ),
            Leaf(
                "agents",
                "Agent integrations",
                "launch",
                "Which AI coding agents OpenContext wires up.",
            ),
            Leaf(
                "plugins",
                "Plugins",
                "launch",
                "Browse and install plugins; set update behaviour.",
            ),
            Leaf(
                "memory",
                "Memory backend",
                "launch",
                "local / engram / auto — offers to install Engram if missing.",
            ),
            Leaf(
                "language",
                "Language",
                "select",
                "Interface language.",
                options=lang_opts,
                current=lang_cur,
                apply=lang_apply,
            ),
            Leaf(
                "sdd_profile",
                "SDD model profile",
                "select",
                "How models are routed across SDD phases.",
                options=opt_list("default", "cheap", "hybrid", "premium"),
                current=prof_cur,
                apply=prof_apply,
            ),
            Leaf(
                "tdd_mode",
                "TDD mode",
                "select",
                "Whether SDD enforces test-first.",
                options=opt_list("ask", "strict", "off"),
                current=tdd_cur,
                apply=tdd_apply,
            ),
        ),
    )
    maintenance = Category(
        "maintenance",
        "Maintenance",
        "3",
        (
            Leaf(
                "show",
                "Show current config",
                "launch",
                "Print the full resolved configuration.",
                run=wizard.show_config,
            ),
            Leaf(
                "reset",
                "Reset to defaults",
                "launch",
                "Restore factory defaults (asks first).",
                run=wizard.reset_config,
            ),
            Leaf("quit", "Quit", "quit", "Leave configuration."),
        ),
    )
    return [setup, settings, maintenance]
