"""Knowledge-graph explorer — a clear, keyboard-navigable graph navigator.

Focus one node; see what it **calls** (→) and what **calls it** (←). Two views,
toggled with Tab:

- **List** — the connections as a selectable list (default; densest, most legible).
- **Graph** — a local diagram: the focus node in the middle, callers branching
  left and callees right, with the selected neighbor highlighted.

Enter walks into the highlighted neighbor (drill down a level), Backspace returns,
a breadcrumb tracks the path. Both views share one cursor, so navigation is
identical either way. A full-knowledge-graph force-directed cloud is just noise in
a terminal, so we render the *local* graph you're actually standing on.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Static

from opencontext_cli.tui.brand import ACCENT, DIM, PRIMARY, SECONDARY, BrandBar
from opencontext_cli.tui.graph.models import GraphMode, GraphNodeKind

_MAX_NEIGHBORS = 40

# Map raw KG node-kind strings → GraphNodeKind → a one-glyph marker, so every row
# carries a consistent icon and unknown kinds never fall through to the wrong
# bucket. (Kind normalization is pinned by tests/honesty.)
_KIND_MAP: dict[str, GraphNodeKind] = {
    "file": GraphNodeKind.FILE,
    "symbol": GraphNodeKind.SYMBOL,
    "memory": GraphNodeKind.MEMORY,
    "agent": GraphNodeKind.AGENT,
    "phase": GraphNodeKind.PHASE,
    "unknown": GraphNodeKind.UNKNOWN,
    "function": GraphNodeKind.SYMBOL,
    "method": GraphNodeKind.SYMBOL,
    "class": GraphNodeKind.SYMBOL,
    "artifact": GraphNodeKind.SYMBOL,
    "variable": GraphNodeKind.FILE,
    "constant": GraphNodeKind.FILE,
}

_KIND_ICON: dict[GraphNodeKind, str] = {
    GraphNodeKind.SYMBOL: "●",
    GraphNodeKind.FILE: "▪",
    GraphNodeKind.MEMORY: "◆",
    GraphNodeKind.AGENT: "▲",
    GraphNodeKind.PHASE: "◉",
    GraphNodeKind.UNKNOWN: "○",
}


def _map_kind(raw: str) -> GraphNodeKind:
    """Return the GraphNodeKind for *raw*, defaulting to UNKNOWN."""
    return _KIND_MAP.get(raw, GraphNodeKind.UNKNOWN)


def _icon(kind: str) -> str:
    """One-glyph marker for a raw kind string."""
    return _KIND_ICON.get(_map_kind(kind), "○")


def _short(label: str, width: int) -> str:
    label = label or ""
    return label if len(label) <= width else label[: max(width - 1, 1)] + "…"


@dataclass(frozen=True)
class Neighbor:
    """One directed connection from the focus node."""

    node_id: str
    label: str
    kind: str
    direction: str  # "calls" (focus → neighbor) or "called by" (neighbor → focus)


def _connect(root: Path | str) -> Any:
    """Open a stable connection to the project's KG SQLite DB (Row factory for
    name access), or None when absent. Uses sqlite3 directly — a short-lived
    GraphDatabase wrapper would be GC'd and close the connection mid-use."""
    import sqlite3

    from opencontext_core.config_resolver import resolve_active_storage_file

    db_path = resolve_active_storage_file(Path(root), "context_graph.db")
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def pick_focus(root: Path | str = ".") -> str | None:
    """The node to open on first — the busiest (highest-degree) one, so the
    explorer lands somewhere connected rather than on an arbitrary leaf."""
    try:
        conn = _connect(root)
        if conn is None:
            return None
        from collections import Counter

        rows = conn.execute(
            "SELECT source_node_id, target_node_id FROM edges "
            "WHERE target_node_id IS NOT NULL LIMIT 8000"
        ).fetchall()
        degree: Counter[str] = Counter()
        for r in rows:
            degree[str(r["source_node_id"])] += 1
            degree[str(r["target_node_id"])] += 1
        return degree.most_common(1)[0][0] if degree else None
    except Exception:
        return None


def load_node_neighbors(
    focus_id: str, root: Path | str = "."
) -> tuple[Neighbor | None, list[Neighbor]]:
    """Return ``(focus, neighbors)`` for *focus_id*.

    ``focus`` is the node itself (None if it isn't in the graph); ``neighbors``
    are its callees (``calls``) then callers (``called by``), de-duplicated and
    capped for a readable list.
    """
    try:
        conn = _connect(root)
        if conn is None:
            return None, []
        frow = conn.execute("SELECT id, name, kind FROM nodes WHERE id = ?", (focus_id,)).fetchone()
        if frow is None:
            return None, []
        focus = Neighbor(str(frow["id"]), str(frow["name"]), str(frow["kind"] or ""), "")

        callee_ids = [
            str(r["target_node_id"])
            for r in conn.execute(
                "SELECT target_node_id FROM edges "
                "WHERE source_node_id = ? AND target_node_id IS NOT NULL LIMIT ?",
                (focus_id, _MAX_NEIGHBORS),
            ).fetchall()
        ]
        caller_ids = [
            str(r["source_node_id"])
            for r in conn.execute(
                "SELECT source_node_id FROM edges WHERE target_node_id = ? LIMIT ?",
                (focus_id, _MAX_NEIGHBORS),
            ).fetchall()
        ]

        def names(ids: list[str]) -> dict[str, tuple[str, str]]:
            ids = [i for i in dict.fromkeys(ids) if i != focus_id]
            if not ids:
                return {}
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT id, name, kind FROM nodes WHERE id IN ({placeholders})", tuple(ids)
            ).fetchall()
            return {str(r["id"]): (str(r["name"]), str(r["kind"] or "")) for r in rows}

        callee_names = names(callee_ids)
        caller_names = names(caller_ids)
        neighbors: list[Neighbor] = []
        seen: set[str] = set()
        for nid in callee_ids:
            if nid in callee_names and nid not in seen:
                seen.add(nid)
                nm, kd = callee_names[nid]
                neighbors.append(Neighbor(nid, nm, kd, "calls"))
        for nid in caller_ids:
            if nid in caller_names and nid not in seen:
                seen.add(nid)
                nm, kd = caller_names[nid]
                neighbors.append(Neighbor(nid, nm, kd, "called by"))
        return focus, neighbors
    except Exception:
        return None, []


class LocalGraphView(Widget):
    """The focus node + its connections, in either a List or a Graph view.

    Owns the cursor so navigation is identical in both views: ↑↓ select, Enter
    drills into the highlighted neighbor (posts ``Drill``), Tab toggles the view.
    """

    can_focus = True

    DEFAULT_CSS = "LocalGraphView { height: 1fr; }"

    class Drill(Message):
        """Posted on Enter — the screen reloads the chosen node's neighborhood."""

        def __init__(self, node_id: str) -> None:
            self.node_id = node_id
            super().__init__()

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("up,k", "cursor(-1)", "Up"),
        Binding("down,j", "cursor(1)", "Down"),
        Binding("enter", "open", "Open"),
        Binding("tab", "toggle_view", "List/Graph"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._focus: Neighbor | None = None
        self._neighbors: list[Neighbor] = []
        self._cursor = 0
        self._view = "list"

    @property
    def view(self) -> str:
        return self._view

    def set_data(self, focus: Neighbor | None, neighbors: list[Neighbor]) -> None:
        self._focus = focus
        self._neighbors = neighbors
        self._cursor = 0
        self._safe_refresh()

    def _safe_refresh(self) -> None:
        try:
            self.refresh()
        except Exception:
            pass

    def action_cursor(self, delta: int) -> None:
        if self._neighbors:
            self._cursor = max(0, min(self._cursor + delta, len(self._neighbors) - 1))
            self._safe_refresh()

    def action_toggle_view(self) -> None:
        self._view = "graph" if self._view == "list" else "list"
        self._safe_refresh()

    def action_open(self) -> None:
        if 0 <= self._cursor < len(self._neighbors):
            self.post_message(self.Drill(self._neighbors[self._cursor].node_id))

    def render(self) -> str:
        if self._focus is None:
            return "[dim]No indexed knowledge graph found.[/]"
        return self._render_graph() if self._view == "graph" else self._render_list()

    def _render_list(self) -> str:
        focus = self._focus
        assert focus is not None
        lines = [f"[bold {PRIMARY}]◉ {focus.label}[/]   [dim]{focus.kind}[/]", ""]
        if not self._neighbors:
            lines.append("[dim]— no outgoing or incoming connections —[/]")
        for i, n in enumerate(self._neighbors):
            arrow = (
                f"[{SECONDARY}]→ calls    [/]"
                if n.direction == "calls"
                else f"[{ACCENT}]← called by[/]"
            )
            row = f"{arrow}  {_icon(n.kind)} {n.label}   [dim]{n.kind}[/]"
            lines.append(f"[bold]▸[/] {row}" if i == self._cursor else f"  {row}")
        return "\n".join(lines)

    def _render_graph(self) -> str:
        focus = self._focus
        assert focus is not None
        width = self.size.width if self.size.width and self.size.width > 30 else 100
        height = self.size.height if self.size.height and self.size.height > 8 else 24
        half = max(width // 2, 18)
        cur = self._neighbors[self._cursor] if 0 <= self._cursor < len(self._neighbors) else None
        callers = [n for n in self._neighbors if n.direction == "called by"]
        callees = [n for n in self._neighbors if n.direction == "calls"]
        cap = max(height - 6, 3)
        hidden = max(len(callers) - cap, 0) + max(len(callees) - cap, 0)

        ftext = f"◉ {focus.label}  ({focus.kind})"
        pad = max((width - len(ftext)) // 2, 0)
        lines = [
            "",
            " " * pad + f"[bold {PRIMARY}]◉ {focus.label}[/]  [dim]({focus.kind})[/]",
            " " * max(half - 1, 0) + f"[{DIM}]│[/]",
            " " * max(half - 2 - len("← called by"), 0)
            + f"[{ACCENT}]← called by[/]   [{SECONDARY}]→ calls[/]",
        ]
        for r in range(min(max(len(callers), len(callees)), cap)):
            left = self._graph_cell(callers[r], "L", half - 4, cur) if r < len(callers) else ""
            right = self._graph_cell(callees[r], "R", half - 4, cur) if r < len(callees) else ""
            left_pad = " " * (half - 2 - _vlen(left)) + left
            lines.append(f"{left_pad}  [{DIM}]│[/]  {right}")
        if hidden:
            lines.append(f"[dim]   … {hidden} more — ↑↓ to reach, enter to open[/]")
        return "\n".join(lines)

    @staticmethod
    def _graph_cell(n: Neighbor, side: str, maxw: int, cur: Neighbor | None) -> str:
        label = _short(n.label, maxw)
        body = f"{label} ●" if side == "L" else f"● {label}"
        return f"[reverse]{body}[/]" if cur is not None and cur.node_id == n.node_id else body


def _vlen(markup: str) -> int:
    """Visible length of a Rich-markup string (strips [...] tags)."""
    import re

    return len(re.sub(r"\[/?[^\]]*\]", "", markup))


class GraphScreen(Screen[None]):
    """Keyboard-navigable knowledge-graph explorer (List + Graph views)."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape,q", "dismiss", "Close"),
        Binding("backspace", "back", "Back"),
    ]

    DEFAULT_CSS = """
    GraphScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #kg-breadcrumb { color: #6C757D; }
    #kg-view { border: round #21262D; padding: 0 1; }
    """

    def __init__(
        self,
        *,
        mode: GraphMode = GraphMode.KG,
        root: Path | str = ".",
        run_id: str | None = None,
        focus_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._mode = mode
        self._root = root
        self._run_id = run_id
        self._path: list[Neighbor] = []  # breadcrumb trail; last = current focus
        self._pending_focus = focus_id
        self._no_tui = not sys.stdout.isatty()

    def compose(self) -> ComposeResult:
        yield BrandBar(root=self._root)
        yield Static("Knowledge graph", id="kg-breadcrumb", markup=True)
        self._view = LocalGraphView(id="kg-view")
        yield self._view
        yield Footer()

    async def on_mount(self) -> None:
        focus_id = self._pending_focus or pick_focus(self._root)
        if focus_id:
            self._go(focus_id)
        else:
            self._view.set_data(None, [])
        self.query_one("#kg-breadcrumb", Static).update(self._breadcrumb())
        try:
            self._view.focus()
        except Exception:
            pass

    def _go(self, focus_id: str) -> None:
        focus, neighbors = load_node_neighbors(focus_id, root=self._root)
        if focus is None:
            return
        self._path.append(focus)
        self._view.set_data(focus, neighbors)
        self.query_one("#kg-breadcrumb", Static).update(self._breadcrumb())

    def _breadcrumb(self) -> str:
        trail = self._path[-5:]
        names = f" [{DIM}]>[/] ".join(n.label for n in trail) if trail else "knowledge graph"
        prefix = f"[{DIM}]…>[/] " if len(self._path) > 5 else ""
        controls = (
            f"  [{DIM}]↑↓ select · enter open · tab list/graph · backspace back · esc close[/]"
        )
        return f"{prefix}{names}{controls}"

    def on_local_graph_view_drill(self, message: LocalGraphView.Drill) -> None:
        self._go(message.node_id)

    def action_back(self) -> None:
        if len(self._path) <= 1:
            return
        self._path.pop()  # drop current
        focus = self._path.pop()  # re-loaded (re-appended) by _go
        self._go(focus.node_id)

    def render_text(self) -> str:
        """Plain-text view for non-TTY / --no-tui."""
        if not self._path:
            return "(no knowledge graph)"
        focus = self._path[-1]
        _, neighbors = load_node_neighbors(focus.node_id, root=self._root)
        lines = [f"◉ {focus.label}  ({focus.kind})"]
        for n in neighbors:
            mark = "->" if n.direction == "calls" else "<-"
            lines.append(f"  {mark} {n.label}  ({n.kind})")
        if not neighbors:
            lines.append("  (no connections)")
        return "\n".join(lines)

    def action_dismiss(self, result: Any = None) -> None:  # type: ignore[override]
        self.app.pop_screen()
