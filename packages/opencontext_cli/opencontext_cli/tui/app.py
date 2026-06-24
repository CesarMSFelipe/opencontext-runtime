"""The unified OpenContext Textual application and its configuration screen.

One ``App`` hosts every screen so all commands share the same chrome, palette and
navigation. The configuration screen is a 3-column Miller drill-down (categories →
settings → options) built from the framework-agnostic model in
``config_model.build_config_model`` — simple settings are picked in place, richer
ones suspend the app to run their existing guided handler, then resume.
"""

from __future__ import annotations

import sys
from typing import Any, ClassVar

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, Static

from opencontext_cli.tui.brand import DIM, PRIMARY, SUCCESS, WARNING, BrandBar


class ConfigScreen(Screen):
    """Configuration as a 3-column Miller menu: Category · Setting · Options."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit_tui", "Quit"),
        Binding("escape", "quit_tui", "Quit", show=False),
        Binding("left", "focus_left", "◀ column", show=False),
        Binding("right", "focus_right", "column ▶", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        from opencontext_cli.tui.config_model import build_config_model

        self.model = build_config_model()
        self.cat_idx = 0
        self.set_idx = 0

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
            sv.append(ListItem(Label(leaf.label)))
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
        if leaf.kind == "select" and leaf.options:
            for val, label in leaf.options():
                mark = "  ✓" if val == current else ""
                ov.append(ListItem(Label(label + mark)))
            ov.index = 0
            info.update(leaf.description)
        else:
            from opencontext_cli.tui.sub_screens import NATIVE_SCREENS

            text = leaf.description
            if current:
                text += f"\n[{_DIM}]current:[/] {current}"
            native = leaf.key in NATIVE_SCREENS
            hint = "Enter → configure" if native else "Enter → open guided setup"
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
            await self._refresh_options()
            self.query_one("#info", Static).update(f"[{SUCCESS}]✓ {message}[/]")

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
            self.app.push_screen(builder(), lambda _r: self.run_worker(after()))
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

    def action_quit_tui(self) -> None:
        self.app.exit()


class HomeScreen(Screen):
    """The OpenContext home — one branded menu for every top-level action."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit_tui", "Quit"),
        Binding("escape", "quit_tui", "Quit", show=False),
    ]
    _ACTIONS: ClassVar[list[tuple[str, str]]] = [
        ("install", "Install / reconfigure"),
        ("upgrade", "Upgrade all packages"),
        ("sync", "Re-sync environment"),
        ("configure", "Settings — providers, agents, plugins, SDD, features…"),
        ("verified", "Verified context for a task"),
        ("memory", "Context memory"),
        ("doctor", "Doctor — health check"),
        ("backups", "Backups"),
        ("uninstall", "Uninstall"),
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
        from opencontext_cli.commands import menu_cmd

        handler = {
            "install": menu_cmd._run_install,
            "upgrade": menu_cmd._run_upgrade,
            "sync": menu_cmd._run_sync,
            "verified": menu_cmd._run_verified_context,
            "memory": menu_cmd._run_memory_tools,
            "doctor": menu_cmd._run_doctor,
            "backups": menu_cmd._run_backups,
            "uninstall": menu_cmd._run_uninstall,
        }.get(key)
        if handler is None:
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

    def action_quit_tui(self) -> None:
        self.app.exit()


class OpenContextApp(App):  # type: ignore[misc]
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

    SCREENS: ClassVar[dict[str, type]] = {"config": ConfigScreen, "home": HomeScreen}

    def __init__(self, start: str = "config") -> None:
        super().__init__()
        self._start = start

    def on_mount(self) -> None:
        if self._start == "cockpit":
            from opencontext_cli.tui.cockpit import CockpitScreen

            self.push_screen(CockpitScreen())
        elif self._start == "home":
            self.push_screen(HomeScreen())
        else:
            self.push_screen(ConfigScreen())


_DIM = "#6C757D"


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
