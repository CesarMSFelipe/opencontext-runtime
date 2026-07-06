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

from opencontext_core.i18n import t


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
    # Dotted key in the resolved OpenContextConfig — lets the TUI show the
    # source layer (defaults/global/project/env/...) next to the setting.
    config_key: str | None = None


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

    def flow_cur() -> str:
        from opencontext_core.config import find_config, load_config

        cf = find_config(".")
        if cf and cf.exists():
            try:
                mode = getattr(load_config(cf).sdd, "flow_mode", None)
                return str(mode) if mode else "hybrid"
            except Exception:
                return "hybrid"
        return "hybrid"

    def flow_apply(val: str) -> str:
        from opencontext_core.config_sync import set_yaml_key

        return f"OC Flow → {val}" if set_yaml_key("sdd.flow_mode", val) else "No opencontext.yaml"

    def opt_list(*vals: str) -> Callable[[], list[tuple[str, str]]]:
        return lambda: [(v, v) for v in vals]

    def desc(*lines: str) -> str:
        return "\n".join(lines)

    project_setup = Category(
        "project_setup",
        t("config.cat.project_setup"),
        "1",
        (
            Leaf(
                "wizard",
                t("config.leaf.wizard"),
                "launch",
                desc(
                    "Current: project-guided setup.",
                    "Effect: writes opencontext.yaml and agent integration files.",
                    "Recommended: run once per project, then use Settings for small changes.",
                    "Risk / note: asks before destructive changes.",
                    "CLI: opencontext config wizard",
                ),
                run=wizard.run_wizard,  # type: ignore[arg-type]
            ),
            Leaf(
                "agents",
                t("config.leaf.agents"),
                "launch",
                desc(
                    "Current: configured agents for this workspace.",
                    "Effect: controls Claude/Codex/OpenCode integration files.",
                    "Recommended: enable only agents you actually use.",
                    "Risk / note: workspace install should not write global agent config.",
                    "CLI: opencontext install --agent <agent> --scope workspace",
                ),
            ),
            Leaf(
                "plugins",
                t("config.leaf.plugins"),
                "launch",
                desc(
                    "Current: installed OpenContext plugins.",
                    "Effect: adds optional commands, skills, and integrations.",
                    "Recommended: keep minimal until a workflow needs a plugin.",
                    "Risk / note: third-party plugins extend local tool surface.",
                    "CLI: opencontext config reconfigure plugins",
                ),
            ),
        ),
    )
    runtime = Category(
        "runtime",
        t("config.cat.runtime"),
        "2",
        (
            Leaf(
                "security",
                t("config.leaf.security"),
                "select",
                desc(
                    "Current: selected security posture.",
                    "Effect: controls external access and provider safety defaults.",
                    "Recommended: local/dev for solo work; enterprise for locked-down orgs.",
                    "Risk / note: lower postures may allow more integrations.",
                    "CLI: opencontext config set security_mode <mode>",
                ),
                options=sec_opts,
                current=sec_cur,
                apply=sec_apply,
                config_key="security.mode",
            ),
            Leaf(
                "features",
                t("config.leaf.features"),
                "launch",
                desc(
                    "Current: feature toggles.",
                    "Effect: enables KG, call graph, learning.",
                    "Recommended: KG on.",
                    "Risk / note: more features can add indexing work.",
                    "CLI: opencontext config set features.<name> true",
                ),
            ),
            Leaf(
                "tokens",
                t("config.leaf.tokens"),
                "launch",
                desc(
                    "Current: default token budget.",
                    "Effect: caps context and agentic phase output.",
                    "Recommended: 8k-16k for normal repos.",
                    "Risk / note: too low can hide needed evidence.",
                    "CLI: opencontext config set default_token_budget <n>",
                ),
            ),
            Leaf(
                "models",
                t("config.leaf.models"),
                "launch",
                desc(
                    "Current: default provider/model and phase routing.",
                    "Effect: used when host-agent/provider execution is enabled.",
                    "Recommended: mock/host-agent for safe local QA.",
                    "Risk / note: real providers can make network/API calls.",
                    "CLI: opencontext models",
                ),
            ),
            Leaf(
                "language",
                t("config.leaf.language"),
                "select",
                desc(
                    "Current: UI language.",
                    "Effect: changes CLI/TUI copy where translations exist.",
                    "Recommended: your team language.",
                    "Risk / note: logs/artifacts may still contain English schema fields.",
                    "CLI: opencontext config set ui_language <en|es>",
                ),
                options=lang_opts,
                current=lang_cur,
                apply=lang_apply,
                config_key="ui_language",
            ),
        ),
    )
    workflow = Category(
        "agentic_workflow",
        t("config.cat.agentic_workflow"),
        "3",
        (
            Leaf(
                "sdd_profile",
                t("config.leaf.sdd_profile"),
                "select",
                desc(
                    "Current: SDD model profile.",
                    "Effect: routes explore/propose/spec/design/tasks/apply/verify.",
                    "Recommended: hybrid for balanced runs.",
                    "Risk / note: premium may cost more; cheap may reduce quality.",
                    "CLI: opencontext config set sdd.model_profile <profile>",
                ),
                options=opt_list("default", "cheap", "hybrid", "premium"),
                current=prof_cur,
                apply=prof_apply,
            ),
            Leaf(
                "tdd_mode",
                t("config.leaf.tdd_mode"),
                "select",
                desc(
                    "Current: TDD enforcement.",
                    "Effect: controls whether apply starts with tests.",
                    "Recommended: strict for core code, ask for exploratory work.",
                    "Risk / note: off can reduce regression coverage.",
                    "CLI: opencontext config set sdd.tdd_mode <ask|strict|off>",
                ),
                options=opt_list("ask", "strict", "off"),
                current=tdd_cur,
                apply=tdd_apply,
                config_key="sdd.tdd_mode",
            ),
            Leaf(
                "oc_flow",
                t("config.leaf.oc_flow"),
                "select",
                desc(
                    "Current: OC Flow execution policy for agentic runs.",
                    "Effect: how the OC Flow harness pauses and executes — automatic "
                    "(no pauses), stepwise (pause every phase), hybrid (pause only at "
                    "risky gates), or observe / engram / openspec-only.",
                    "Recommended: hybrid for human-in-the-loop; automatic for CI.",
                    "Risk / note: automatic runs phases without pausing for approval.",
                    "CLI: opencontext config set sdd.flow_mode <mode>",
                ),
                options=opt_list(
                    "automatic",
                    "stepwise",
                    "hybrid",
                    "engram_only",
                    "openspec_only",
                    "observe_only",
                ),
                current=flow_cur,
                apply=flow_apply,
                config_key="sdd.flow_mode",
            ),
        ),
    )
    memory = Category(
        "memory",
        t("config.cat.memory"),
        "4",
        (
            Leaf(
                "memory",
                t("config.leaf.memory"),
                "launch",
                desc(
                    "Current: local / engram / auto.",
                    "Effect: controls what phase memory reads/writes.",
                    "Recommended: auto if Engram is installed; local otherwise.",
                    "Risk / note: Engram is external; local is project-scoped.",
                    "CLI: opencontext config set memory.provider auto",
                ),
                config_key="memory.provider",
            ),
        ),
    )
    maintenance = Category(
        "maintenance",
        t("config.cat.maintenance"),
        "5",
        (
            Leaf(
                "show",
                t("config.leaf.show"),
                "launch",
                desc(
                    "Current: resolved config view.",
                    "Effect: prints what OpenContext will use now.",
                    "Recommended: check before debugging installs/runs.",
                    "Risk / note: may include local paths.",
                    "CLI: opencontext config show",
                ),
                run=wizard.show_config,
            ),
            Leaf(
                "reset",
                t("config.leaf.reset"),
                "launch",
                desc(
                    "Current: reset action.",
                    "Effect: restores user config defaults.",
                    "Recommended: only when config is confusing.",
                    "Risk / note: asks first; can remove preferences.",
                    "CLI: opencontext config reset",
                ),
                run=wizard.reset_config,
            ),
            Leaf("quit", t("config.leaf.quit"), "quit", "Leave configuration."),
        ),
    )
    return [project_setup, runtime, workflow, memory, maintenance]
