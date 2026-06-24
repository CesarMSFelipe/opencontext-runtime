"""Native Textual screens for the config settings that need more than a pick.

These replace the InquirerPy guided flows for the simple cases (toggles, a typed
value, a single pick) so the whole config experience stays inside the one branded
app instead of dropping to a different prompt system. Each screen reads and writes
the same stores the CLI handlers use, so behaviour is unchanged — only the chrome.

Genuinely multi-step settings (Providers & models, Plugins) still suspend to their
existing guided handlers; converting those is the remaining tail.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, OptionList, SelectionList
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from opencontext_cli.tui.brand import BrandBar


class _ModalBase(ModalScreen):
    DEFAULT_CSS = """
    _ModalBase { align: center middle; background: #0B0F14; }
    _ModalBase > Vertical {
        width: 80; height: auto; max-height: 90%;
        border: round #00C9A7; background: #0B0F14; padding: 1 2;
    }
    _ModalBase .title { color: #00C9A7; text-style: bold; padding: 0 0 1 0; }
    _ModalBase Input, _ModalBase SelectionList, _ModalBase OptionList {
        background: #0B0F14; border: round #6C757D;
    }
    """


class MultiToggleScreen(_ModalBase):
    """A checkbox screen (space toggles, s saves) — used for features / agents."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        title: str,
        items: Sequence[tuple[str, str, bool]],
        on_save: Callable[[list[str]], None],
    ) -> None:
        super().__init__()
        self._title = title
        self._items = items
        self._on_save = on_save

    def compose(self) -> ComposeResult:
        with Vertical():
            yield BrandBar()
            yield Label(self._title, classes="title")
            yield SelectionList[str](
                *[Selection(label, key, enabled) for key, label, enabled in self._items],
                id="sel",
            )
            yield Footer()

    def on_mount(self) -> None:
        self.query_one(SelectionList).focus()

    def action_save(self) -> None:
        selected = list(self.query_one(SelectionList).selected)
        self._on_save(selected)
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class TextValueScreen(_ModalBase):
    """A single typed value (Enter saves) — used for token budgets."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        current: str,
        on_save: Callable[[str], None],
        *,
        numeric: bool = False,
    ) -> None:
        super().__init__()
        self._title = title
        self._current = current
        self._on_save = on_save
        self._numeric = numeric

    def compose(self) -> ComposeResult:
        with Vertical():
            yield BrandBar()
            yield Label(self._title, classes="title")
            yield Input(
                value=self._current,
                type="integer" if self._numeric else "text",
                id="val",
            )
            yield Footer()

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if value:
            self._on_save(value)
        self.dismiss(bool(value))

    def action_cancel(self) -> None:
        self.dismiss(False)


class PickOneScreen(_ModalBase):
    """A single-choice screen (Enter picks) — used for the memory backend."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        title: str,
        options: Sequence[tuple[str, str]],
        on_pick: Callable[[str], None],
    ) -> None:
        super().__init__()
        self._title = title
        self._options = options
        self._on_pick = on_pick

    def compose(self) -> ComposeResult:
        with Vertical():
            yield BrandBar()
            yield Label(self._title, classes="title")
            yield OptionList(*[Option(label, id=key) for key, label in self._options])
            yield Footer()

    def on_mount(self) -> None:
        ol = self.query_one(OptionList)
        ol.highlighted = 0  # so Enter works without moving first
        ol.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self._on_pick(event.option.id)
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


# ── Builders: wire each native screen to the same stores the CLI handlers use ──


def _prefs() -> Any:
    from opencontext_core.user_prefs import UserConfigStore

    return UserConfigStore()


def features_screen() -> MultiToggleScreen:
    keys = [
        ("knowledge_graph", "Knowledge Graph"),
        ("call_graph", "Call Graph"),
        ("learning_system", "Learning System"),
    ]
    store = _prefs()
    prefs = store.load()
    items = [(k, label, bool(getattr(prefs.features, k))) for k, label in keys]

    def save(selected: list[str]) -> None:
        p = store.load()
        for k, _ in keys:
            setattr(p.features, k, k in selected)
        store.save(p)

    return MultiToggleScreen("Features", items, save)


def agents_screen() -> MultiToggleScreen:
    store = _prefs()
    prefs = store.load()
    agent_keys = list(prefs.agent_integrations.keys())
    items = [(a, a, bool(prefs.agent_integrations[a])) for a in agent_keys]

    def save(selected: list[str]) -> None:
        p = store.load()
        for a in agent_keys:
            p.agent_integrations[a] = a in selected
        store.save(p)

    return MultiToggleScreen("Agent integrations", items, save)


def tokens_screen() -> TextValueScreen:
    store = _prefs()
    current = str(store.load().default_token_budget)

    def save(value: str) -> None:
        try:
            n = max(1000, min(100000, int(value)))
        except ValueError:
            return
        p = store.load()
        p.default_token_budget = n
        store.save(p)

    return TextValueScreen("Default token budget", current, save, numeric=True)


def memory_screen() -> PickOneScreen:
    from opencontext_core.config_sync import set_yaml_key

    options = [
        ("local", "Local — OpenContext's own engine"),
        ("engram", "Engram — episodic & semantic → Engram, rest → OpenContext"),
        ("auto", "Auto — couple with Engram if present, else local"),
    ]

    def pick(value: str) -> None:
        set_yaml_key("memory.provider", value)

    return PickOneScreen("Memory backend", options, pick)


class ModelsScreen(_ModalBase):
    """Two-step provider → model pick (saved to prefs + mirrored to yaml)."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel", show=False),
    ]
    _PROVIDERS: ClassVar[list[str]] = ["anthropic", "openai", "mock"]
    _MODELS: ClassVar[dict[str, list[str]]] = {
        "anthropic": ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"],
        "openai": ["gpt-4o", "gpt-4o-mini", "o1"],
        "mock": ["mock-llm"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._provider: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield BrandBar()
            yield Label("Providers & models", classes="title")
            yield Label("1 · Provider")
            yield OptionList(*[Option(p, id=p) for p in self._PROVIDERS], id="prov")
            yield Label("2 · Model")
            yield OptionList(id="mod")
            yield Footer()

    def on_mount(self) -> None:
        prov = self.query_one("#prov", OptionList)
        prov.highlighted = 0  # so Enter works without moving first
        prov.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "prov":
            self._provider = event.option.id
            mod = self.query_one("#mod", OptionList)
            mod.clear_options()
            for m in self._MODELS.get(self._provider or "", []):
                mod.add_option(Option(m, id=m))
            mod.highlighted = 0  # highlight the first model so Enter saves it
            mod.focus()
        elif event.option_list.id == "mod" and self._provider and event.option.id:
            self._save(self._provider, event.option.id)
            self.dismiss(True)

    def _save(self, provider: str, model: str) -> None:
        from opencontext_core.config_sync import sync_runtime_prefs_to_yaml

        store = _prefs()
        p = store.load()
        p.default_provider = provider
        p.default_model = model
        store.save(p)
        try:
            sync_runtime_prefs_to_yaml(p)
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(False)


def models_screen() -> ModelsScreen:
    return ModelsScreen()


def plugins_screen() -> MultiToggleScreen:
    """Plugins as toggles: the two update prefs + each available plugin to install."""
    store = _prefs()
    prefs = store.load()
    items: list[tuple[str, str, bool]] = [
        ("__check__", "Check for updates automatically", bool(prefs.check_updates)),
        ("__auto__", "Auto-update plugins", bool(prefs.auto_update_plugins)),
    ]
    try:
        from opencontext_core.plugin_system import PluginRegistry, RegistryFetcher

        installed = {p.name for p in PluginRegistry().discover()}
        fetcher = RegistryFetcher()
        try:
            available = fetcher.fetch()
        except Exception:
            available = fetcher.search()
        for plug in available:
            if plug.name not in installed:
                items.append(
                    (f"plugin:{plug.name}", f"install {plug.name} — {plug.description[:38]}", False)
                )
    except Exception:
        pass

    def save(selected: list[str]) -> None:
        p = store.load()
        p.check_updates = "__check__" in selected
        p.auto_update_plugins = "__auto__" in selected
        store.save(p)
        names = [s.split(":", 1)[1] for s in selected if s.startswith("plugin:")]
        if names:
            try:
                from opencontext_core.plugin_system import PluginInstaller, PluginRegistry

                installer = PluginInstaller(PluginRegistry())
                for name in names:
                    installer.install_from_registry(name)
            except Exception:
                pass

    return MultiToggleScreen("Plugins", items, save)


# Config leaf key → native screen builder. Keys not here keep their guided handler.
NATIVE_SCREENS: dict[str, Callable[[], ModalScreen]] = {
    "features": features_screen,
    "agents": agents_screen,
    "tokens": tokens_screen,
    "memory": memory_screen,
    "models": models_screen,
    "plugins": plugins_screen,
}
