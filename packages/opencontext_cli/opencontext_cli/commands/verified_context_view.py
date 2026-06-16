"""Rendering helpers for the interactive menu's knowledge-graph and verified-context views.

These functions are deliberately free of prompts and I/O side effects so they can be
unit-tested directly: gathering the index status returns plain data, and the renderers
return Rich renderables that can be exported to a string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass
class KnowledgeGraphStatus:
    """Plain summary of the local index, suitable for the menu header."""

    indexed: bool
    files: int = 0
    symbols: int = 0
    nodes: int = 0
    edges: int = 0
    generated_at: datetime | None = None
    profiles: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def age_label(self) -> str:
        """Human-readable freshness derived from the manifest timestamp."""
        if self.generated_at is None:
            return "unknown"
        moment = self.generated_at
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - moment
        seconds = max(0, int(delta.total_seconds()))
        if seconds < 90:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"


def gather_kg_status(root: str | Path = ".") -> KnowledgeGraphStatus:
    """Read index statistics from the persisted manifest and knowledge-graph database.

    Never raises: an un-indexed or unreadable project yields ``indexed=False`` with a
    short human-readable reason in ``detail``.
    """
    project_root = Path(root).resolve()
    storage_path = project_root / ".storage" / "opencontext"
    config_path = project_root / "opencontext.yaml"

    try:
        from opencontext_core.runtime import OpenContextRuntime

        runtime = OpenContextRuntime(
            config_path=str(config_path) if config_path.exists() else None,
            storage_path=storage_path,
        )
    except Exception as exc:
        return KnowledgeGraphStatus(indexed=False, detail=f"runtime unavailable: {exc}")

    try:
        manifest = runtime.load_manifest()
    except Exception:
        return KnowledgeGraphStatus(
            indexed=False,
            detail="not indexed — run 'opencontext index .'",
        )

    nodes = 0
    edges = 0
    try:
        graph_stats = runtime.knowledge_graph.get_stats()
        nodes = int(graph_stats.get("nodes", 0))
        edges = int(graph_stats.get("edges", 0))
    except Exception:
        # Call graph is optional; symbol/file counts still convey value.
        nodes = int(manifest.metadata.get("knowledge_graph", {}).get("nodes", 0))

    return KnowledgeGraphStatus(
        indexed=True,
        files=len(manifest.files),
        symbols=len(manifest.symbols),
        nodes=nodes,
        edges=edges,
        generated_at=manifest.generated_at,
        profiles=list(manifest.technology_profiles),
    )


def render_kg_header(status: KnowledgeGraphStatus) -> Panel:
    """Render the knowledge-graph status header shown at the top of the menu."""
    if not status.indexed:
        body = Text.from_markup(
            f"[yellow]●[/] Not indexed   [dim]{status.detail}[/]",
        )
        return Panel(
            body,
            title="[dim]Knowledge Graph[/]",
            border_style="yellow",
            padding=(0, 1),
        )

    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="left")
    grid.add_column(justify="left")
    grid.add_column(justify="left")
    grid.add_row(
        f"[bold #00C9A7]{status.files}[/] files",
        f"[bold #00A8E8]{status.symbols}[/] symbols",
        f"[bold #845EC2]{status.nodes}[/] graph nodes",
    )
    grid.add_row(
        f"[bold #845EC2]{status.edges}[/] call edges",
        f"[dim]indexed[/] {status.age_label}",
        f"[dim]{', '.join(status.profiles) if status.profiles else 'no profiles'}[/]",
    )
    return Panel(
        grid,
        title="[dim]Knowledge Graph[/]   [green]● indexed[/]",
        border_style="#00C9A7",
        padding=(0, 1),
    )


def _gate_outcome(result: Any) -> tuple[int, int, bool]:
    """Return (passed, total, all_passed) for the gates on a verified-context result."""
    gates = list(getattr(result, "gates", []) or [])
    passed = sum(1 for gate in gates if getattr(gate, "passed", False))
    total = len(gates)
    return passed, total, total > 0 and passed == total


def _trust_value(result: Any) -> str:
    """Extract the planner trust status as a lowercase string."""
    decision = getattr(result, "trust_decision", None)
    status = getattr(decision, "status", decision)
    if isinstance(status, dict):
        status = status.get("status", "")
    return str(status or "").lower()


def _risk_value(result: Any) -> str:
    """Extract the risk level as a lowercase string (enum or raw)."""
    risk = getattr(result, "risk_level", "")
    return str(getattr(risk, "value", risk) or "").lower()


def trust_badge(result: Any) -> Text:
    """Compute a green/amber/red trust badge from gates and the trust decision."""
    _passed, _total, all_passed = _gate_outcome(result)
    trust = _trust_value(result)
    risk = _risk_value(result)

    if all_passed and trust == "sufficient":
        return Text("● TRUSTED", style="bold green")
    if not all_passed or trust == "insufficient":
        if risk == "high":
            return Text("● UNVERIFIED", style="bold red")
        return Text("● PARTIAL", style="bold yellow")
    return Text("● PARTIAL", style="bold yellow")


def aicx_reduction_pct(result: Any) -> float | None:
    """Estimate the AICX token reduction percent from the result's own fields.

    Original token cost is the sum of evidence tokens; the AICX bytecode cost is
    estimated from the compact transport dict (≈ 4 chars per token, matching the
    runtime's own metric). Returns ``None`` when there is nothing to compress.
    """
    evidence = list(getattr(result, "evidence", []) or [])
    original = sum(int(getattr(item, "tokens", 0)) for item in evidence)
    if original <= 0:
        return None

    aicx = getattr(result, "aicx", None)
    if not aicx:
        return None

    instructions = aicx.get("i", []) if isinstance(aicx, dict) else []
    dictionary = aicx.get("d", {}) if isinstance(aicx, dict) else {}
    rendered_chars = len(str(aicx.get("v", ""))) + len(str(aicx.get("chk", "")))
    for row in instructions:
        rendered_chars += sum(len(str(part)) for part in row) + len(row)
    for key, value in dictionary.items():
        rendered_chars += len(str(key)) + len(str(value))
    bytecode_tokens = max(1, rendered_chars // 4)

    reduction = max(0.0, (1 - bytecode_tokens / original) * 100)
    return round(reduction, 1)


def _token_summary_line(result: Any) -> str:
    """Build the token-usage / reduction line from token_usage and AICX metrics."""
    usage = getattr(result, "token_usage", {}) or {}
    final = usage.get("final_context_pack")
    baseline = usage.get("baseline_project")

    parts: list[str] = []
    if final is not None:
        parts.append(f"[bold]{final}[/] tokens in context pack")
    if baseline:
        try:
            saved = max(0.0, (1 - int(final or 0) / int(baseline)) * 100)
            parts.append(f"[green]{saved:.0f}% smaller[/] than full repo ({baseline} tokens)")
        except (TypeError, ZeroDivisionError, ValueError):
            pass

    reduction = aicx_reduction_pct(result)
    if reduction is not None:
        parts.append(f"AICX transport: [green]{reduction:.0f}% fewer[/] tokens")

    if not parts:
        return "[dim]no token usage recorded[/]"
    return "   ".join(parts)


def _gates_table(result: Any) -> Table:
    """Render the per-gate pass/fail table."""
    table = Table(show_header=True, header_style="dim", box=None, padding=(0, 1))
    table.add_column("", width=2)
    table.add_column("Gate", style="bold")
    table.add_column("Result")
    for gate in getattr(result, "gates", []) or []:
        passed = bool(getattr(gate, "passed", False))
        icon = "[green]✓[/]" if passed else "[red]✗[/]"
        reason = getattr(gate, "reason", "")
        outcome = "[green]pass[/]" if passed else f"[red]fail[/] [dim]{reason}[/]"
        table.add_row(icon, str(getattr(gate, "name", "?")), outcome)
    return table


def _sources_lines(result: Any) -> list[str]:
    """Summarize included evidence/memory sources and omitted ones."""
    lines: list[str] = []
    sources: list[str] = []
    for item in getattr(result, "evidence", []) or []:
        sources.append(str(getattr(item, "source", "")))
    for item in getattr(result, "memory", []) or []:
        sources.append(f"{getattr(item, 'source', '')} [dim](memory)[/]")

    if sources:
        for src in sources[:6]:
            lines.append(f"  [#00A8E8]•[/] {src}")
        if len(sources) > 6:
            lines.append(f"  [dim]… and {len(sources) - 6} more[/]")
    else:
        lines.append("  [dim]no sources included[/]")

    omitted = list(getattr(result, "omitted_sources", []) or [])
    if omitted:
        lines.append(f"  [dim]omitted: {', '.join(omitted)}[/]")
    return lines


def render_verified_context(result: Any, *, query: str = "") -> Panel:
    """Render a scannable result card for a verified-context run."""
    passed, total, _all = _gate_outcome(result)
    badge = trust_badge(result)
    risk = _risk_value(result) or "unknown"
    risk_style = {"low": "green", "normal": "green", "high": "red"}.get(risk, "yellow")

    header = Table.grid(padding=(0, 2))
    header.add_column()
    header.add_column()
    header.add_column()
    header.add_row(
        badge,
        Text.from_markup(f"[dim]gates[/] {passed}/{total} passed"),
        Text.from_markup(f"[dim]risk[/] [{risk_style}]{risk}[/]"),
    )

    sections: list[RenderableType] = [header, Text("")]
    sections.append(_gates_table(result))
    sections.append(Text(""))
    sections.append(Text.from_markup(_token_summary_line(result)))
    sections.append(Text(""))
    sections.append(Text.from_markup("[dim]Included sources[/]"))
    for line in _sources_lines(result):
        sections.append(Text.from_markup(line))

    trace = getattr(result, "trace_id", "")
    title = "[bold]Verified context[/]"
    if query:
        title += f"   [dim]{query}[/]"
    return Panel(
        Group(*sections),
        title=title,
        subtitle=f"[dim]trace {trace}[/]" if trace else None,
        border_style=risk_style if risk != "high" else "red",
        padding=(1, 2),
    )


def renderable_to_text(renderable: RenderableType, *, width: int = 100) -> str:
    """Render a Rich renderable to plain text (used by tests and non-TTY callers).

    Writes to an in-memory sink so it has no stdout side effects.
    """
    import io

    from rich.console import Console

    buffer = Console(
        record=True,
        width=width,
        force_terminal=False,
        color_system=None,
        file=io.StringIO(),
    )
    buffer.print(renderable)
    return buffer.export_text()
