"""RunsScreen / RunDetailScreen — browse persisted runs from both layouts.

Runs live under ``<root>/.opencontext/runs/<run_id>/`` (harness) and
``<root>/.opencontext/sessions/<session_id>/runs/<run_id>/`` (OC Flow /
durable apply). The list shows every run newest first; Enter opens the
evidence detail (gates, verification, TDD block, changed files) with a raw
JSON toggle.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, Static

from opencontext_cli.tui.brand import DIM, ERROR, PRIMARY, SUCCESS, BrandBar

_GATE_ICONS = {"passed": "✓", "failed": "✗", "skipped": "-"}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _canonical(status: str) -> str:
    try:
        from opencontext_core.models.canonical_status import to_canonical

        return to_canonical(status).value
    except Exception:
        return status


def _run_dir_candidates(root: Path) -> list[Path]:
    """Run directories from both on-disk layouts."""
    candidates: list[Path] = []
    runs_dir = root / ".opencontext" / "runs"
    if runs_dir.is_dir():
        candidates.extend(d for d in sorted(runs_dir.iterdir()) if d.is_dir())
    sessions_dir = root / ".opencontext" / "sessions"
    if sessions_dir.is_dir():
        for session_dir in sorted(sessions_dir.iterdir()):
            runs_subdir = session_dir / "runs"
            if runs_subdir.is_dir():
                candidates.extend(d for d in sorted(runs_subdir.iterdir()) if d.is_dir())
    return candidates


def list_run_rows(root: Path) -> list[dict[str, Any]]:
    """One row per persisted run in either layout, newest first."""
    rows: list[dict[str, Any]] = []
    for run_dir in _run_dir_candidates(root):
        manifest_path = run_dir / "run.json"
        data = _read_json(manifest_path)
        if data is None:
            # OC Flow's legacy state.json carries the same surface fields.
            manifest_path = run_dir / "state.json"
            data = _read_json(manifest_path)
        if not isinstance(data, dict):
            continue
        try:
            mtime = manifest_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        rows.append(
            {
                "run_id": str(data.get("run_id", run_dir.name)),
                "workflow": str(data.get("workflow") or "?"),
                "status": str(
                    data.get("canonical_status") or _canonical(str(data.get("status", "")))
                ),
                "task": str(data.get("task") or ""),
                "created_at": str(data.get("created_at") or ""),
                "run_dir": run_dir,
                "mtime": mtime,
            }
        )
    rows.sort(key=lambda r: (r["created_at"], r["mtime"]), reverse=True)
    return rows


def load_run_detail(run_dir: Path) -> dict[str, Any]:
    """The evidence bundle for one run: manifest, gates, verification, TDD."""
    run = _read_json(run_dir / "run.json") or _read_json(run_dir / "state.json") or {}
    if not isinstance(run, dict):
        run = {}
    # OC Flow keeps a copy under artifacts/oc-flow/ — fall back like `runs show`.
    oc_dir = run_dir / "artifacts" / "oc-flow"
    gates_doc = _read_json(run_dir / "gates.json") or _read_json(oc_dir / "gates.json") or {}
    raw_gates = gates_doc.get("gates", []) if isinstance(gates_doc, dict) else []
    gates = [
        {"name": str(g.get("name") or g.get("id") or "?"), "status": str(g.get("status", "?"))}
        for g in raw_gates
        if isinstance(g, dict)
    ]
    verification = (
        _read_json(run_dir / "verification.json") or _read_json(oc_dir / "verification.json") or {}
    )
    tdd = run.get("tdd")
    changed = run.get("changed_files") or []
    return {
        "run": run,
        "gates": gates,
        "verification": verification if isinstance(verification, dict) else {},
        "tdd": tdd if isinstance(tdd, dict) else None,
        "changed_files": [str(c) for c in changed] if isinstance(changed, list) else [],
    }


class RunsScreen(Screen[None]):
    """Persisted runs from both layouts, newest first — Enter opens detail."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape,q", "dismiss", "Back"),
    ]

    DEFAULT_CSS = """
    RunsScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #runs-list { height: 1fr; }
    """

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self._root = root or Path(".")
        self._rows: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield BrandBar()
        yield Static(
            "[bold]Runs[/]\n[dim]Persisted harness and OC Flow runs — Enter opens detail[/]",
            markup=True,
        )
        yield ListView(id="runs-list")
        yield Static("", id="runs-empty", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._rows = list_run_rows(self._root)
        lv = self.query_one("#runs-list", ListView)
        for row in self._rows:
            lv.append(
                ListItem(
                    Label(
                        f"{escape(row['run_id'])}  [{PRIMARY}]{escape(row['workflow'])}[/]  "
                        f"{escape(row['status'])}  [{DIM}]{escape(row['task'][:48])}[/]"
                    )
                )
            )
        if self._rows:
            lv.index = 0
            lv.focus()
        else:
            self.query_one("#runs-empty", Static).update("[dim]No persisted runs found.[/dim]")

    @on(ListView.Selected, "#runs-list")
    def _open_detail(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is not None and index < len(self._rows):
            self.app.push_screen(RunDetailScreen(self._rows[index]["run_dir"]))

    def action_dismiss(self, result: Any = None) -> None:  # type: ignore[override]
        self.app.pop_screen()


class RunDetailScreen(Screen[None]):
    """Gates, verification, TDD evidence and changed files for one run."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape,q", "dismiss", "Back"),
        Binding("j", "toggle_raw", "Raw JSON"),
    ]

    DEFAULT_CSS = """
    RunDetailScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #run-detail { height: 1fr; }
    """

    def __init__(self, run_dir: Path) -> None:
        super().__init__()
        self._run_dir = run_dir
        self._raw = False

    def compose(self) -> ComposeResult:
        yield BrandBar()
        yield Static(
            "[bold]Run detail[/]\n[dim]Gates, verification and evidence — j toggles raw JSON[/]",
            markup=True,
        )
        yield Static("", id="run-detail", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self.query_one("#run-detail", Static).update(self._detail_markup())

    def _detail_markup(self) -> str:
        detail = load_run_detail(self._run_dir)
        if self._raw:
            payload = {
                "run": detail["run"],
                "gates": detail["gates"],
                "verification": detail["verification"],
            }
            return escape(json.dumps(payload, indent=2, default=str))
        run = detail["run"]
        if not run:
            return "[dim]run.json not found in this run directory.[/dim]"
        status = str(run.get("canonical_status") or run.get("status") or "?")
        status_color = SUCCESS if status in ("passed", "completed") else ERROR
        lines = [
            f"[bold]Run:[/] {escape(str(run.get('run_id', self._run_dir.name)))}",
            f"[bold]Workflow:[/] {escape(str(run.get('workflow') or '?'))}",
            f"[bold]Status:[/] [{status_color}]{escape(status)}[/]",
            f"[bold]Task:[/] {escape(str(run.get('task') or ''))}",
        ]
        if detail["gates"]:
            lines.append("")
            lines.append("[bold]Gates:[/]")
            for gate in detail["gates"]:
                icon = _GATE_ICONS.get(gate["status"], "?")
                color = SUCCESS if gate["status"] == "passed" else ERROR
                if gate["status"] == "skipped":
                    color = DIM
                lines.append(
                    f"  [{color}]{icon}[/] {escape(gate['name'])}  {escape(gate['status'])}"
                )
        verification = detail["verification"]
        if verification:
            lines.append("")
            lines.append("[bold]Verification:[/]")
            lines.append(f"  outcome: {escape(str(verification.get('outcome', '?')))}")
            commands = verification.get("commands") or []
            if isinstance(commands, list) and commands:
                lines.append(f"  commands: {escape(', '.join(str(c) for c in commands))}")
        tdd = detail["tdd"]
        if tdd:
            lines.append("")
            lines.append("[bold]TDD:[/]")
            for key, value in tdd.items():
                lines.append(f"  {escape(str(key))}: {escape(json.dumps(value, default=str))}")
        if detail["changed_files"]:
            lines.append("")
            lines.append("[bold]Changed files:[/]")
            lines.extend(f"  • {escape(path)}" for path in detail["changed_files"])
        return "\n".join(lines)

    def action_toggle_raw(self) -> None:
        self._raw = not self._raw
        self._refresh()

    def action_dismiss(self, result: Any = None) -> None:  # type: ignore[override]
        self.app.pop_screen()
