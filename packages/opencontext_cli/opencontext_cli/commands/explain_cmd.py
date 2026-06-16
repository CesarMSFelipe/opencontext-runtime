"""Explain CLI — make the "verified, minimal context" promise visible.

`opencontext explain "<task>"` shows WHY each file is in the context pack (the
signal that selected it), what was kept out and why, and the token economics — so
the agent's context is auditable instead of a black box.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


def add_explain_parser(subparsers: Any) -> None:
    """Add the ``explain`` command parser."""
    parser = subparsers.add_parser(
        "explain",
        help="Explain why each file is (or isn't) in the context for a task.",
        description=(
            "Build the context for a task and explain it: which files were "
            "selected and by what signal, what was kept out and why, and the "
            "token cost — the audit trail behind verified context.\n\n"
            '  opencontext explain "fix the login bug"\n'
        ),
    )
    parser.add_argument("query", help="The task or question to build context for.")
    parser.add_argument("--root", default=".", help="Project root (default: .).")
    parser.add_argument("--max-tokens", type=int, default=None, help="Context token budget.")


def _why(item: Any) -> str:
    """A short, human reason this item was selected, from its decision metadata."""
    md = getattr(item, "metadata", None) or {}
    parts: list[str] = []
    source = md.get("retrieval_source") or md.get("source_type")
    if source:
        parts.append(str(source))
    retrieval = md.get("retrieval") or {}
    node, kind = retrieval.get("node"), retrieval.get("kind")
    if node and kind:
        parts.append(f"{kind} {node}")
    rels = retrieval.get("relationships") or []
    if "search_match" in rels:
        parts.append("matched query")
    elif rels:
        parts.append(", ".join(rels))
    if getattr(item, "redacted", False) or md.get("redacted"):
        parts.append("secret redacted")
    return " · ".join(parts) or "ranked candidate"


def handle_explain(runtime: Any, args: Any) -> int:
    """Render the why-this-context view. Returns a process exit code."""
    root = Path(args.root)
    if args.root != "." and root.exists():
        runtime.index_project(root)

    pack = runtime.build_context_pack(args.query, args.max_tokens)
    included = list(pack.included)
    omitted = list(pack.omitted)
    reasons = {o.item_id: o.reason for o in pack.omissions}

    console.print(f"\n[bold]Why this context[/] — [italic]{args.query}[/]")
    redacted = sum(1 for it in included if getattr(it, "redacted", False))
    summary = f"{len(included)} files · {pack.used_tokens:,} tokens"
    if redacted:
        summary += f" · {redacted} with secrets redacted"
    console.print(f"[dim]{summary}[/]\n")

    if included:
        table = Table(show_edge=False, pad_edge=False, box=None)
        table.add_column("file", style="cyan", no_wrap=False)
        table.add_column("score", justify="right", style="green")
        table.add_column("tok", justify="right", style="dim")
        table.add_column("why")
        for item in included:
            table.add_row(item.source, f"{item.score:.2f}", f"{item.tokens:,}", _why(item))
        console.print(table)
    else:
        console.print("[yellow]No files selected for this task.[/]")

    if omitted:
        console.print("\n[dim]Kept out (and why):[/]")
        for item in omitted:
            reason = reasons.get(item.id, "below the budget/diversity cut")
            console.print(f"  [dim]✗[/] {item.source}  [dim]{item.tokens:,} tok — {reason}[/]")

    freshness_nudge(runtime, root)
    return 0


def freshness_nudge(runtime: Any, root: Path) -> None:
    """Warn if the index drifted from disk (stale context erodes trust). Best-effort."""
    try:
        report = runtime.knowledge_graph.stale_files(root)
    except Exception:
        return
    if report.total:
        console.print(
            f"\n[yellow]⚠ Index is {report.total} files behind the working tree[/] — "
            "run [cyan]opencontext index .[/] for fresh context."
        )
