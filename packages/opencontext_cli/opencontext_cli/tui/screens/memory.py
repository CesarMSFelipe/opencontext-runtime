"""MemoryBrowserScreen — v2 observations with approval-lifecycle actions.

Lists the workspace's ``memory_v2.db`` observations (id, lifecycle state,
title, type, trust, expiry, origin) newest first. ``t`` cycles a type filter.
``a`` approves and ``x`` rejects the selected ``proposed`` memory through the
same :func:`opencontext_memory.mem_approve` /
:func:`opencontext_memory.mem_reject` entry points the
``opencontext memory approve|reject`` CLI verbs use; reject asks for
confirmation first. Non-proposed rows are a no-op with a status-bar hint.

The store tracks no numeric confidence; the trust column is honestly derived
from the real lifecycle fields (``pinned``, ``lifecycle_state``,
``review_after``) via :func:`trust_label`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Label, ListItem, ListView, Static

from opencontext_cli.tui.brand import DIM, SUCCESS, WARNING, BrandBar

_STATE_COLORS = {"proposed": WARNING, "active": SUCCESS}
_PAST_TENSE = {"approve": "approved", "reject": "rejected"}


def _store_db_path(root: Path) -> Path:
    from opencontext_core.paths import StorageMode, resolve_storage_path

    return resolve_storage_path(root, StorageMode.local) / "memory_v2.db"


def _open_store(root: Path) -> Any:
    """The workspace v2 observations store (same store the CLI verbs use)."""
    from opencontext_memory import MemoryStore

    return MemoryStore.open(_store_db_path(root))


def list_memory_rows(root: Path, *, type_filter: str | None = None) -> list[dict[str, Any]]:
    """Live observations (id, lifecycle_state, title, type, session_id, scope,
    pinned, review_after), newest first; optionally narrowed to one type."""
    if not _store_db_path(root).is_file():
        return []
    store = _open_store(root)
    try:
        query = """
            SELECT id, title, type, lifecycle_state, created_at,
                   session_id, scope, pinned, review_after
            FROM observations
            WHERE deleted_at IS NULL
        """
        params: tuple[Any, ...] = ()
        if type_filter is not None:
            query += " AND type = ?"
            params = (type_filter,)
        query += " ORDER BY id DESC LIMIT 200"
        with store._connect() as conn:  # read-only inspection handle
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        store.close()


def trust_label(row: dict[str, Any]) -> str:
    """Derived trust for one observation row — from real lifecycle fields only.

    ``pinned`` rows are explicitly protected; ``proposed`` rows are not yet
    approved (unverified); an overdue ``review_after`` means stale context
    (needs_review); everything else is approved, current memory (trusted).
    """
    if int(row.get("pinned") or 0):
        return "pinned"
    if str(row.get("lifecycle_state")) == "proposed":
        return "unverified"
    from opencontext_memory.lifecycle import state

    if state(row.get("review_after")) == "needs_review":
        return "needs_review"
    return "trusted"


class RejectConfirmScreen(ModalScreen[bool]):
    """Confirm rejecting one proposed memory — y rejects, n/escape cancels."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("y", "confirm", "Reject"),
        Binding("n,escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    RejectConfirmScreen { align: center middle; background: #0B0F14 60%; }
    RejectConfirmScreen > Vertical {
        width: 70; height: auto; border: round #FF6F91;
        background: #0B0F14; padding: 1 2;
    }
    """

    def __init__(self, title: str) -> None:
        super().__init__()
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[bold]Reject memory?[/]")
            yield Static(
                f"{escape(self._title)}\n\n"
                f"[{DIM}]Rejected memories are never retrieved again. "
                "y rejects · n cancels[/]",
                markup=True,
            )
            yield Footer()

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class MemoryBrowserScreen(Screen[None]):
    """Workspace memories with lifecycle state — a approves, x rejects proposed,
    t cycles the type filter."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape,q", "dismiss", "Back"),
        Binding("a", "approve", "Approve"),
        Binding("x", "reject", "Reject"),
        Binding("t", "cycle_filter", "Filter type"),
    ]

    DEFAULT_CSS = """
    MemoryBrowserScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #memory-list { height: 1fr; }
    #memory-status { height: auto; }
    """

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self._root = root or Path(".")
        self._rows: list[dict[str, Any]] = []
        self._type_filter: str | None = None

    def compose(self) -> ComposeResult:
        yield BrandBar()
        yield Static(
            "[bold]Memory[/]\n"
            "[dim]Workspace memories — a approves, x rejects the selected proposed row, "
            "t filters by type[/]",
            markup=True,
        )
        yield ListView(id="memory-list")
        yield Static("", id="memory-empty", markup=True)
        yield Static("", id="memory-status", markup=True)
        yield Footer()

    async def on_mount(self) -> None:
        await self._reload()

    @staticmethod
    def _row_label(row: dict[str, Any]) -> str:
        state = str(row["lifecycle_state"])
        color = _STATE_COLORS.get(state, DIM)
        expiry = str(row.get("review_after") or "none")
        origin = str(row.get("session_id") or "?")
        return (
            f"#{row['id']}  [{color}]{escape(state)}[/]  "
            f"{escape(str(row['title']))}  [{DIM}]{escape(str(row['type']))}[/]  "
            f"{escape(trust_label(row))}  [{DIM}]exp:{escape(expiry)}  from:{escape(origin)}[/]"
        )

    async def _reload(self) -> None:
        self._rows = list_memory_rows(self._root, type_filter=self._type_filter)
        lv = self.query_one("#memory-list", ListView)
        await lv.clear()
        for row in self._rows:
            lv.append(ListItem(Label(self._row_label(row))))
        empty = self.query_one("#memory-empty", Static)
        if self._rows:
            empty.update("")
            lv.index = 0
            lv.focus()
        elif self._type_filter is not None:
            empty.update(f"[dim]No memories of type '{escape(self._type_filter)}'.[/dim]")
        else:
            empty.update("[dim]No memories found in the workspace store.[/dim]")

    async def action_cycle_filter(self) -> None:
        """Cycle the type filter: all → each stored type (sorted) → all."""
        types = sorted({str(row["type"]) for row in list_memory_rows(self._root)})
        if not types:
            self._set_status("[dim]No memories to filter.[/dim]")
            return
        if self._type_filter is None:
            self._type_filter = types[0]
        else:
            index = types.index(self._type_filter) + 1 if self._type_filter in types else 0
            self._type_filter = types[index] if index < len(types) else None
        await self._reload()
        label = self._type_filter if self._type_filter is not None else "all"
        self._set_status(f"Type filter: [bold]{escape(label)}[/]")

    def _selected_row(self) -> dict[str, Any] | None:
        index = self.query_one("#memory-list", ListView).index
        if index is None or index >= len(self._rows):
            return None
        return self._rows[index]

    def _set_status(self, message: str) -> None:
        self.query_one("#memory-status", Static).update(message)

    async def _apply_lifecycle(self, verb: str, row: dict[str, Any]) -> None:
        from opencontext_memory import mem_approve, mem_reject

        handler = mem_approve if verb == "approve" else mem_reject
        store = _open_store(self._root)
        try:
            result = handler(store, observation_id=int(row["id"]))
        except Exception as exc:
            self._set_status(f"[bold]{verb} failed:[/] {escape(str(exc))}")
            return
        finally:
            store.close()
        await self._reload()
        self._set_status(
            f"Memory #{result['id']} {_PAST_TENSE[verb]} — "
            f"now [bold]{escape(str(result['lifecycle_state']))}[/]."
        )

    async def action_approve(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        if str(row["lifecycle_state"]) != "proposed":
            self._set_status(f"[{DIM}]Only proposed memories can be approved.[/]")
            return
        await self._apply_lifecycle("approve", row)

    def action_reject(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        if str(row["lifecycle_state"]) != "proposed":
            self._set_status(f"[{DIM}]Only proposed memories can be rejected.[/]")
            return

        async def _on_confirm(confirmed: bool | None) -> None:
            if confirmed:
                await self._apply_lifecycle("reject", row)

        self.app.push_screen(RejectConfirmScreen(str(row["title"])), _on_confirm)

    def action_dismiss(self, result: Any = None) -> None:  # type: ignore[override]
        self.app.pop_screen()
