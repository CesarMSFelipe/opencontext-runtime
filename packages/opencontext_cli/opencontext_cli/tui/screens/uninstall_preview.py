"""UninstallPreviewScreen — read-only dry-run plan for uninstall.

Imports the same plan sources the ``uninstall`` command uses
(``Configurator.deconfigure(dry_run=True)`` for agent config, the v2 install
manifest / legacy purge targets for managed paths). Strictly a preview — the
TUI never deletes anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static

from opencontext_cli.tui.brand import DIM, WARNING, BrandBar


def build_uninstall_preview(root: Path) -> dict[str, Any]:
    """The uninstall dry-run plan: agent removals + managed paths."""
    from opencontext_cli.commands.uninstall_cmd import _PURGE_TARGETS, _load_v2_manifest
    from opencontext_core.configurator import Configurator

    configurator = Configurator(project_root=root)
    agents = configurator.detect_installed()
    report = configurator.deconfigure(agents, dry_run=True) if agents else {"results": []}
    manifest = _load_v2_manifest(root)
    if manifest is not None:
        managed = {
            "source": "manifest",
            "created_paths": [str(p) for p in manifest.get("created_paths") or []],
            "state_paths": [str(p) for p in manifest.get("state_paths") or []],
            "modified_files": [str(p) for p in manifest.get("modified_files") or []],
        }
    else:
        managed = {
            "source": "legacy",
            "created_paths": [str(t) for t in _PURGE_TARGETS],
            "state_paths": [],
            "modified_files": [],
        }
    return {"agents": agents, "results": report.get("results", []), "managed_paths": managed}


class UninstallPreviewScreen(Screen[None]):
    """Read-only uninstall dry-run: what would be removed, and from where."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape,q", "dismiss", "Back"),
    ]

    DEFAULT_CSS = """
    UninstallPreviewScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #uninstall-preview-content { height: 1fr; }
    """

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self._root = root or Path(".")

    def compose(self) -> ComposeResult:
        yield BrandBar()
        yield Static(
            "[bold]Uninstall preview[/]\n"
            f"[{WARNING}]Dry run — nothing is removed from this screen.[/] "
            "[dim]Use 'opencontext uninstall' to apply.[/dim]",
            markup=True,
        )
        yield Static("", id="uninstall-preview-content", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#uninstall-preview-content", Static).update(self._screen_markup())

    def _screen_markup(self) -> str:
        try:
            preview = build_uninstall_preview(self._root)
        except Exception as exc:  # a plan failure must render, not crash
            return f"[red]Could not build the uninstall plan: {escape(str(exc))}[/red]"
        lines: list[str] = []
        if preview["agents"]:
            lines.append("[bold]Agent config removals:[/]")
            for result in preview["results"]:
                lines.append(f"  [bold]{escape(str(result.get('agent', '?')))}[/]")
                for action in result.get("plan", []):
                    if isinstance(action, dict):
                        verb = str(action.get("action", "change"))
                        path = str(action.get("path", ""))
                        lines.append(f"    [{DIM}]{escape(verb)} {escape(path)}[/]")
                    else:
                        lines.append(f"    [{DIM}]{escape(str(action))}[/]")
        else:
            lines.append("[dim]No configured agents detected.[/dim]")
        managed = preview["managed_paths"]
        lines.append("")
        lines.append(f"[bold]Managed paths[/] [{DIM}](source: {escape(managed['source'])})[/]")
        for path in managed["created_paths"]:
            lines.append(f"  • {escape(path)}")
        for path in managed["state_paths"]:
            lines.append(f"  • {escape(path)} [{DIM}](state)[/]")
        for path in managed["modified_files"]:
            lines.append(f"  • {escape(path)} [{DIM}](managed block only)[/]")
        return "\n".join(lines)

    def action_dismiss(self, result: Any = None) -> None:  # type: ignore[override]
        self.app.pop_screen()
