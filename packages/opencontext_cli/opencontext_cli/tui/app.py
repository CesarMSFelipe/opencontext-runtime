"""The unified OpenContext Textual application and its configuration screen.

One ``App`` hosts every screen so all commands share the same chrome, palette and
navigation. The configuration screen is a 3-column Miller drill-down (categories →
settings → options) built from the framework-agnostic model in
``config_model.build_config_model`` — simple settings are picked in place, richer
ones suspend the app to run their existing guided handler, then resume.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, Static

from opencontext_cli.tui.brand import DIM, PRIMARY, SUCCESS, WARNING, BrandBar


class ConfigScreen(Screen[None]):
    """Configuration as a 3-column Miller menu: Category · Setting · Options.

    ``v`` surfaces the validation panel: schema diagnostics from
    ``config doctor``, cross-layer conflicts, and the active overrides.
    """

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("q", "quit_tui", "Quit"),
        Binding("escape", "quit_tui", "Quit", show=False),
        Binding("left", "focus_left", "◀ column", show=False),
        Binding("right", "focus_right", "column ▶", show=False),
        Binding("v", "show_validation", "Validation"),
    ]

    def __init__(self) -> None:
        super().__init__()
        from opencontext_cli.tui.config_model import build_config_model

        self.model = build_config_model()
        self.cat_idx = 0
        self.set_idx = 0
        self._sources = _config_sources()

    def _source_of(self, leaf: Any) -> str:
        """Winning resolver layer for a leaf's config key ('' when unmapped)."""
        key = getattr(leaf, "config_key", None)
        if not key or not self._sources:
            return ""
        return self._sources.get(key, "defaults")

    def compose(self) -> ComposeResult:
        yield BrandBar()
        with Horizontal(id="columns"):
            yield ListView(id="cats")
            yield ListView(id="settings")
            yield ListView(id="options")
        yield Static("", id="info", markup=True)
        yield Footer()

    async def on_mount(self) -> None:
        cats = self.query_one("#cats", ListView)
        for cat in self.model:
            cats.append(ListItem(Label(cat.label)))
        cats.index = 0
        cats.focus()
        await self._refresh_settings()

    # ── column population ────────────────────────────────────────────────────
    def _leaf(self) -> Any:
        leaves = self.model[self.cat_idx].leaves
        return leaves[self.set_idx] if self.set_idx < len(leaves) else None

    async def _refresh_settings(self) -> None:
        sv = self.query_one("#settings", ListView)
        await sv.clear()  # async — must complete before re-appending
        for leaf in self.model[self.cat_idx].leaves:
            label = leaf.label
            source = self._source_of(leaf)
            if source:
                label = f"{label}  [{_DIM}]({source})[/]"
            sv.append(ListItem(Label(label)))
        sv.index = 0
        self.set_idx = 0
        await self._refresh_options()

    async def _refresh_options(self) -> None:
        leaf = self._leaf()
        ov = self.query_one("#options", ListView)
        await ov.clear()
        info = self.query_one("#info", Static)
        if leaf is None:
            info.update("")
            return
        current = leaf.current() if leaf.current else ""
        source = self._source_of(leaf)
        source_line = f"\n[{_DIM}]source: {source}[/]" if source else ""
        if leaf.kind == "select" and leaf.options:
            for val, label in leaf.options():
                mark = "  ✓" if val == current else ""
                ov.append(ListItem(Label(label + mark)))
            ov.index = 0
            info.update(leaf.description + source_line)
        else:
            from opencontext_cli.tui.sub_screens import NATIVE_SCREENS

            text = leaf.description
            if current:
                text += f"\n[{_DIM}]current:[/] {current}"
            native = leaf.key in NATIVE_SCREENS
            hint = "Enter → configure" if native else "Enter → open guided setup"
            text += source_line
            text += f"\n\n[{_DIM}]{hint}[/]"
            info.update(text)

    # ── highlight follows the cursor in each column ──────────────────────────
    @on(ListView.Highlighted, "#cats")
    async def _on_cat(self, event: ListView.Highlighted) -> None:
        if event.list_view.index is not None and event.list_view.index != self.cat_idx:
            self.cat_idx = event.list_view.index
            await self._refresh_settings()

    @on(ListView.Highlighted, "#settings")
    async def _on_set(self, event: ListView.Highlighted) -> None:
        if event.list_view.index is not None and event.list_view.index != self.set_idx:
            self.set_idx = event.list_view.index
            await self._refresh_options()

    # ── Enter: drill / launch / apply, depending on the focused column ───────
    @on(ListView.Selected)
    async def _on_select(self, event: ListView.Selected) -> None:
        which = event.list_view.id
        if which == "cats":
            self.query_one("#settings", ListView).focus()
        elif which == "settings":
            leaf = self._leaf()
            if leaf is None:
                return
            if leaf.kind == "quit":
                self.action_quit_tui()
            elif leaf.kind == "select":
                self.query_one("#options", ListView).focus()
            else:
                await self._launch(leaf)
        elif which == "options":
            await self._apply_option()

    async def _apply_option(self) -> None:
        leaf = self._leaf()
        ov = self.query_one("#options", ListView)
        if leaf and leaf.kind == "select" and leaf.options and leaf.apply and ov.index is not None:
            value = leaf.options()[ov.index][0]
            message = leaf.apply(value)
            if leaf.key == "language":
                # Re-translate the menu live so the language switch is visible
                # without a relaunch.
                from opencontext_cli.tui.config_model import build_config_model
                from opencontext_core.i18n import set_language

                set_language(value)
                self.model = build_config_model()
                await self._rebuild_columns()
            else:
                await self._refresh_options()
            self.query_one("#info", Static).update(f"[{SUCCESS}]✓ {message}[/]")

    async def _rebuild_columns(self) -> None:
        """Repopulate every column from ``self.model`` — used after a live
        language switch so category/setting labels re-render in the new language."""
        cats = self.query_one("#cats", ListView)
        await cats.clear()
        for cat in self.model:
            cats.append(ListItem(Label(cat.label)))
        self.cat_idx = min(self.cat_idx, len(self.model) - 1)
        cats.index = self.cat_idx
        await self._refresh_settings()

    async def _after_memory(self) -> None:
        """After the memory pick: refresh, and if the chosen backend needs Engram but
        it's not installed, suspend to offer provisioning it (same as the old flow)."""
        await self._refresh_options()
        try:
            from opencontext_core.config import find_config, load_config
            from opencontext_core.memory.engram_bridge import detect_engram

            provider = "local"
            cf = find_config(".")
            if cf is not None and cf.exists():
                provider = getattr(getattr(load_config(cf), "memory", None), "provider", "local")
            if provider in ("engram", "auto") and not detect_engram():
                from opencontext_cli.commands.menu_cmd import _offer_engram_install

                with self.app.suspend():
                    _offer_engram_install()
        except Exception:
            pass

    async def _launch(self, leaf: Any) -> None:
        # Native Textual modal where we have one (features/agents/tokens/memory);
        # refresh the options column once it's dismissed so the new value shows.
        from opencontext_cli.tui.sub_screens import NATIVE_SCREENS

        builder = NATIVE_SCREENS.get(getattr(leaf, "key", ""))
        if builder is not None:
            after = self._after_memory if leaf.key == "memory" else self._refresh_options
            self.app.push_screen(builder(), lambda _r: self.run_worker(after()))  # type: ignore[arg-type]
            return

        if leaf.run is None:
            return
        from opencontext_core import prompts
        from opencontext_core.dx.console_styles import console

        with self.app.suspend():
            try:
                console.clear()
            except Exception:
                pass
            try:
                leaf.run()
            except Exception as exc:  # one handler must never kill the menu
                console.print(f"[red]{leaf.label} failed: {exc}[/]")
            prompts.pause("Press Enter to return to the menu")
        await self._refresh_options()

    # ── navigation ───────────────────────────────────────────────────────────
    _COLUMNS = ("cats", "settings", "options")

    def _focused_column(self) -> str:
        focused = self.focused
        if focused is not None and focused.id in self._COLUMNS:
            return focused.id
        return "cats"

    def action_focus_left(self) -> None:
        i = self._COLUMNS.index(self._focused_column())
        if i > 0:
            self.query_one(f"#{self._COLUMNS[i - 1]}", ListView).focus()

    def action_focus_right(self) -> None:
        i = self._COLUMNS.index(self._focused_column())
        if i >= len(self._COLUMNS) - 1:
            return
        if self._COLUMNS[i + 1] == "options":
            leaf = self._leaf()
            if not (leaf and leaf.kind == "select"):
                return
        self.query_one(f"#{self._COLUMNS[i + 1]}", ListView).focus()

    def action_show_validation(self) -> None:
        """Render validation diagnostics + layer conflicts into the info panel."""
        info = self.query_one("#info", Static)
        try:
            report = build_config_validation(".")
        except Exception as exc:  # the panel must render, never crash the menu
            info.update(f"[red]Validation unavailable: {exc}[/red]")
            return
        lines: list[str] = []
        diags = report["diagnostics"]
        failed = [d for d in diags if d["status"] == "failed"]
        warned = [d for d in diags if d["status"] == "warning"]
        lines.append(
            f"[bold]Validation:[/] {len(diags)} check(s) — "
            f"{len(failed)} failed · {len(warned)} warning(s)"
        )
        for diag in (*failed, *warned)[:8]:
            mark = "✗" if diag["status"] == "failed" else "!"
            lines.append(f"  {mark} {diag['name']} — {diag['message']}")
        conflicts = report["conflicts"]
        if conflicts:
            lines.append(f"[bold]Conflicts:[/] {len(conflicts)} key(s) set by multiple layers")
            for key, detail in list(conflicts.items())[:8]:
                layers = " → ".join(detail["layers"])
                lines.append(f"  {key}: {layers} [{_DIM}](winner: {detail['winner']})[/]")
        else:
            lines.append("[bold]Conflicts:[/] none")
        overrides = report["overrides"]
        lines.append(f"[bold]Active overrides:[/] {len(overrides)} key(s) set above defaults")
        info.update("\n".join(lines))

    def action_quit_tui(self) -> None:
        self.app.exit()


def build_config_validation(root: str | Path = ".") -> dict[str, Any]:
    """Validation + conflict report for the config inspector (TUI-006).

    Returns ``diagnostics`` (the ``config doctor`` findings), ``conflicts``
    (dotted keys set by two or more non-default layers, with the layer list
    and the winning layer), and ``overrides`` (dotted key → winning layer for
    every key resolved above the defaults layer).
    """
    from opencontext_core.config_doctor import validate
    from opencontext_core.config_resolver import resolve

    diagnostics = [
        {"name": d.name, "status": d.status, "message": d.message} for d in validate(root)
    ]
    provenance = resolve(root).provenance
    overrides = {
        key: layer for key, layer in provenance.by_dotted_key.items() if layer != "defaults"
    }
    conflicts: dict[str, dict[str, Any]] = {}
    for key, layers in provenance.dotted_key_layers.items():
        non_default = [layer for layer in layers if layer != "defaults"]
        if len(non_default) > 1:
            conflicts[key] = {"layers": layers, "winner": provenance.by_dotted_key.get(key)}
    return {"diagnostics": diagnostics, "conflicts": conflicts, "overrides": overrides}


class HomeScreen(Screen[None]):
    """The OpenContext home — one branded menu for every top-level action."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("q", "quit_tui", "Quit"),
        Binding("escape", "quit_tui", "Quit", show=False),
    ]
    _ACTIONS: ClassVar[list[tuple[str, str]]] = [
        ("cockpit", "Main · Cockpit / active run"),
        ("runs", "Main · Runs"),
        ("tdd_gates", "Main · TDD Gates"),
        ("new_change", "Main · Start new change"),
        ("verified", "Main · Build verified context"),
        ("graph", "Main · Knowledge graph"),
        ("memory", "Main · Memory"),
        ("sdd", "Main · SDD workspace"),
        ("harness", "Main · Harness & quality gates"),
        ("receipt", "Main · Receipts / audit trail"),
        ("install", "Setup · Install / reconfigure"),
        ("configure", "Setup · Settings"),
        ("doctor", "Setup · Doctor"),
        ("benchmark", "Setup · Benchmark"),
        ("backups", "Setup · Backups"),
        ("uninstall_preview", "Setup · Uninstall preview"),
        ("uninstall", "Setup · Uninstall"),
        ("quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield BrandBar()
        yield Static(self._kg_line(), id="kg", markup=True)
        yield ListView(id="home")
        yield Footer()

    def on_mount(self) -> None:
        lv = self.query_one("#home", ListView)
        for _key, label in self._ACTIONS:
            lv.append(ListItem(Label(label)))
        lv.index = 0
        lv.focus()

    def _kg_line(self) -> str:
        lines: list[str] = []
        try:
            from opencontext_cli.commands.verified_context_view import gather_kg_status

            s = gather_kg_status(".")
            if s.indexed:
                lines.append(
                    f"  [{PRIMARY}]●[/] indexed · [bold]{s.files}[/] files · "
                    f"[bold]{s.symbols}[/] symbols · [bold]{s.nodes}[/] nodes · "
                    f"[bold]{s.edges}[/] call edges"
                )
            else:
                lines.append(f"  [{DIM}]○ {s.detail}[/]")
        except Exception:
            pass
        try:
            from opencontext_core.update import pending_update_notices

            notices = pending_update_notices()
            if notices:
                lines.append(
                    f"  [{WARNING}]Updates available:[/] {', '.join(notices)} "
                    f"[{DIM}](Upgrade all packages)[/]"
                )
        except Exception:
            pass
        return "\n".join(lines)

    @on(ListView.Selected, "#home")
    async def _on_select(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None:
            return
        key = self._ACTIONS[index][0]
        if key == "quit":
            self.app.exit()
            return
        if key == "configure":
            self.app.push_screen(ConfigScreen())
            return
        if key == "cockpit":
            from opencontext_cli.tui.cockpit import CockpitScreen

            self.app.push_screen(CockpitScreen())
            return
        if key == "new_change":
            from opencontext_cli.tui.cockpit import start_new_change

            start_new_change(
                self.app, refresh=lambda: self.query_one("#kg", Static).update(self._kg_line())
            )
            return
        if key == "graph":
            from opencontext_cli.tui.graph.models import GraphMode
            from opencontext_cli.tui.screens.graph import GraphScreen

            self.app.push_screen(GraphScreen(mode=GraphMode.KG, root=Path(".")))
            return
        if key == "runs":
            from opencontext_cli.tui.screens.runs import RunsScreen

            self.app.push_screen(RunsScreen())
            return
        if key == "tdd_gates":
            from opencontext_cli.tui.screens.tdd_gates import TddGatesScreen

            self.app.push_screen(TddGatesScreen())
            return
        if key == "sdd":
            from opencontext_cli.tui.screens.sdd import SddScreen

            self.app.push_screen(SddScreen())
            return
        if key == "doctor":
            from opencontext_cli.tui.screens.doctor import DoctorScreen

            self.app.push_screen(DoctorScreen())
            return
        if key == "uninstall_preview":
            from opencontext_cli.tui.screens.uninstall_preview import UninstallPreviewScreen

            self.app.push_screen(UninstallPreviewScreen())
            return
        if key in {"harness", "receipt"}:
            run_dir = _latest_run_dir()
            if key == "harness":
                from opencontext_cli.tui.screens.harness import HarnessPanel

                self.app.push_screen(HarnessPanel(run_dir=run_dir))
            else:
                from opencontext_cli.tui.screens.receipt import ReceiptViewer

                self.app.push_screen(ReceiptViewer(run_dir=run_dir))
            return
        from opencontext_cli.commands import menu_cmd

        handler = {
            "install": menu_cmd._run_install,
            "verified": menu_cmd._run_verified_context,
            "memory": menu_cmd._run_memory_tools,
            "backups": menu_cmd._run_backups,
            "uninstall": menu_cmd._run_uninstall,
        }.get(key)
        if handler is None:
            if key == "benchmark":
                self._run_cli(["benchmark", "list"])
            return
        from opencontext_core import prompts
        from opencontext_core.dx.console_styles import console

        with self.app.suspend():
            try:
                console.clear()
            except Exception:
                pass
            try:
                handler()
            except Exception as exc:  # one action must never kill the home menu
                console.print(f"[red]{key} failed: {exc}[/]")
            prompts.pause("Press Enter to return to the menu")
        self.query_one("#kg", Static).update(self._kg_line())

    def _run_cli(self, args: list[str]) -> None:
        from opencontext_core import prompts
        from opencontext_core.dx.console_styles import console

        with self.app.suspend():
            try:
                console.clear()
            except Exception:
                pass
            try:
                from opencontext_cli.main import main

                old_argv = sys.argv
                sys.argv = ["opencontext", *args]
                try:
                    main()
                finally:
                    sys.argv = old_argv
            except SystemExit:
                pass
            except Exception as exc:
                console.print(f"[red]{' '.join(args)} failed: {exc}[/]")
            prompts.pause("Press Enter to return to the menu")
        self.query_one("#kg", Static).update(self._kg_line())

    def action_quit_tui(self) -> None:
        self.app.exit()


class OpenContextApp(App[None]):
    """The single OpenContext TUI application — every screen shares this shell."""

    CSS = """
    Screen { background: #0B0F14; color: #E6EDF3; }
    #columns { height: 1fr; padding: 0 1; }
    #cats { width: 30; }
    #settings { width: 46; }
    #options { width: 1fr; }
    ListView { background: #0B0F14; border: round #6C757D; padding: 0 1; }
    ListView:focus { border: round #00C9A7; }
    #info { height: auto; min-height: 3; padding: 1 2; color: #6C757D; }
    #kg { height: auto; padding: 1 2 0 2; }
    #home { height: 1fr; margin: 1 1; }
    Footer { background: #11161D; }
    """

    SCREENS: ClassVar[dict[str, Callable[[], Screen[Any]]]] = {
        "config": ConfigScreen,
        "home": HomeScreen,
    }

    def __init__(self, start: str = "config", root: str | Path = ".") -> None:
        super().__init__()
        self._start = start
        self._root = Path(root)

    def on_mount(self) -> None:
        if self._start == "cockpit":
            from opencontext_cli.tui.cockpit import CockpitScreen

            self.push_screen(CockpitScreen())
        elif self._start == "home":
            self.push_screen(HomeScreen())
        elif self._start == "error":
            from opencontext_cli.tui.screens.workspace_error import WorkspaceErrorScreen

            self.push_screen(WorkspaceErrorScreen(root=self._root))
        else:
            self.push_screen(ConfigScreen())


_DIM = "#6C757D"


def _config_sources() -> dict[str, str]:
    """Dotted config key → winning layer, from the layered resolver.

    Best-effort: an unresolvable config must never block the settings menu.
    """
    try:
        from opencontext_core.config_resolver import resolve

        return dict(resolve(".").provenance.by_dotted_key)
    except Exception:
        return {}


def _latest_run_dir() -> Path | None:
    try:
        from opencontext_core.oc_new.store import OcNewStore

        state = OcNewStore(".").latest()
        if state is None:
            return None
        return Path(".opencontext") / "runs" / state.identity.run_id
    except Exception:
        return None


def run_config_tui(*, headless: bool = False) -> bool:
    """Open the configuration screen. Returns False when there's no terminal (the
    caller should fall back to the single-column selector); True after exit."""
    if not headless and not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    OpenContextApp(start="config").run()
    return True


def run_home_tui(*, headless: bool = False) -> bool:
    """Open the home menu. Returns False when there's no terminal (caller should
    fall back to the single-column selector); True after exit."""
    if not headless and not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    OpenContextApp(start="home").run()
    return True


def run_cockpit_tui(*, headless: bool = False) -> bool:
    """Open the cockpit screen (default bare-opencontext entry).

    Returns False when there's no terminal; True after exit.
    """
    if not headless and not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    OpenContextApp(start="cockpit").run()
    return True
