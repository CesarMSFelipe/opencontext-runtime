"""ContextViewerScreen — renders the latest run's context pack (TUI-003, CTX-008).

Prefers the persisted ``context-pack.json`` of the most recent run and renders
its TUI-003 fields: included files/symbols, included memory, KG edges used,
token estimates, applied compression, and the mandatory ``context`` metrics
block. Falls back to the latest ``<phase>.context.json`` dump when no pack has
been persisted yet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static

from opencontext_cli.tui.brand import BrandBar

# Pack metrics keys rendered verbatim from the mandatory ``context`` block
# (KG_CONTEXT_COMPRESSION_CONTRACT).
_METRIC_KEYS = (
    "budget_tokens",
    "input_tokens_estimated",
    "output_tokens_estimated",
    "compression_ratio",
    "kg_nodes_used",
    "kg_edges_used",
    "test_nodes_included",
    "memory_hits",
    "protected_spans",
    "protected_spans_kept",
    "excluded_files",
)


def _is_memory_item(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata") or {}
    return item.get("source_type") == "memory" or metadata.get("retrieval_source") == "memory"


def _kg_edges(item: dict[str, Any]) -> list[str]:
    provenance = (item.get("metadata") or {}).get("graph_provenance") or {}
    relationships = provenance.get("relationships") or []
    return [str(rel) for rel in relationships]


def render_pack_view(pack: dict[str, Any], *, pack_name: str = "context-pack.json") -> str:
    """Render a persisted context pack dict into the TUI-003 pack view text.

    Pure and display-only: shows included files/symbols, included memory, KG
    edges used, token estimates, applied compression, and the metrics block.
    """
    included = [item for item in pack.get("included") or [] if isinstance(item, dict)]
    memory_items = [item for item in included if _is_memory_item(item)]
    code_items = [item for item in included if not _is_memory_item(item)]
    edges: list[str] = []
    for item in included:
        edges.extend(_kg_edges(item))

    lines: list[str] = [f"[bold]Pack:[/] {pack_name}", ""]

    lines.append(f"[bold]Included files/symbols ({len(code_items)}):[/]")
    if code_items:
        for item in code_items:
            kind = (item.get("metadata") or {}).get("symbol_kind") or item.get("source_type", "")
            lines.append(f"  - {item.get('source', '?')} [{kind}] {item.get('tokens', 0)} tokens")
    else:
        lines.append("  [dim]none[/dim]")

    lines.append("")
    lines.append(f"[bold]Memory included ({len(memory_items)}):[/]")
    if memory_items:
        for item in memory_items:
            lines.append(f"  - {item.get('source', '?')} {item.get('tokens', 0)} tokens")
    else:
        lines.append("  [dim]none[/dim]")

    lines.append("")
    lines.append(f"[bold]KG edges used ({len(edges)}):[/]")
    if edges:
        lines.extend(f"  - {edge}" for edge in edges)
    else:
        lines.append("  [dim]none[/dim]")

    used = pack.get("used_tokens", 0)
    available = pack.get("available_tokens", 0)
    lines.append("")
    lines.append(f"[bold]Tokens:[/] used {used} / budget {available}")

    compression = pack.get("compression")
    lines.append("")
    if isinstance(compression, dict) and compression.get("enabled"):
        lines.append(
            "[bold]Compression:[/] applied — "
            f"{compression.get('tokens_before', 0)} -> {compression.get('tokens_after', 0)} tokens "
            f"({compression.get('items_compressed', 0)} item(s))"
        )
    else:
        lines.append("[bold]Compression:[/] not applied")

    metrics = pack.get("context")
    lines.append("")
    lines.append("[bold]Metrics:[/]")
    if isinstance(metrics, dict):
        for key in _METRIC_KEYS:
            if key in metrics:
                lines.append(f"  {key}: {metrics[key]}")
        reason = metrics.get("kg_reason")
        if reason:
            lines.append(f"  kg_reason: {reason}")
    else:
        lines.append("  [dim]no metrics block persisted[/dim]")

    return "\n".join(lines)


def latest_pack_path(root: Path) -> Path | None:
    """The most recent persisted ``context-pack.json`` across both run layouts."""
    workspace = root / ".opencontext"
    candidates = list(workspace.glob("runs/*/context-pack.json"))
    candidates.extend(workspace.glob("sessions/*/runs/*/context-pack.json"))
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


class ContextViewerScreen(Screen[None]):
    """Shows the latest run's context pack (TUI-003) or phase context fallback."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape,q", "dismiss", "Back"),
    ]

    DEFAULT_CSS = """
    ContextViewerScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #context-content { height: 1fr; overflow-y: auto; }
    """

    def compose(self) -> ComposeResult:
        yield BrandBar()
        yield Static(
            "[bold]Context pack[/]\n[dim]Latest pack and metrics for the active run[/]",
            markup=True,
        )
        yield Static("", id="context-content", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        content = self.query_one("#context-content", Static)
        content.update(self._render_context())

    def _render_context(self) -> str:
        try:
            pack_path = latest_pack_path(Path())
            if pack_path is not None:
                pack = json.loads(pack_path.read_text(encoding="utf-8"))
                return render_pack_view(pack, pack_name=pack_path.parent.name)
            return self._render_phase_context_fallback()
        except Exception as exc:
            return f"[dim]Context unavailable: {exc}[/dim]"

    def _render_phase_context_fallback(self) -> str:
        """Legacy fallback: dump the latest <phase>.context.json for oc-new runs."""
        from opencontext_core.oc_new.store import OcNewStore

        store = OcNewStore(".")
        state = store.latest()
        if state is None:
            return "[dim]No active run — no context to display.[/dim]"

        run_dir = Path(".opencontext") / "runs" / state.identity.run_id
        # Find the most recent <phase>.context.json file.
        context_files = sorted(run_dir.glob("*.context.json"), key=lambda p: p.stat().st_mtime)
        if not context_files:
            return f"[dim]No context files found for run {state.identity.run_id}.[/dim]"

        latest = context_files[-1]
        data = json.loads(latest.read_text())
        # Show first 2000 chars to avoid flooding the screen.
        text = json.dumps(data, indent=2)[:2000]
        return f"[bold]Context:[/] {latest.name}\n\n{text}"

    def action_dismiss(self, result: Any = None) -> None:  # type: ignore[override]
        self.app.pop_screen()
