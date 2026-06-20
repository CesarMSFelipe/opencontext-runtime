"""Demo CLI — the 30-second "aha" on the user's own repo.

`opencontext demo` shows the before/after that makes the value undeniable: how
many tokens an agent would read by ingesting the whole project, versus the
handful of files OpenContext hands it for a real task — measured, on THIS repo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console

from opencontext_cli.commands.explain_cmd import _why
from opencontext_core.evaluation.telemetry import estimate_naive_tokens

console = Console()

_DEFAULT_QUERY = "How does this project work?"


def add_demo_parser(subparsers: Any) -> None:
    """Add the ``demo`` command parser."""
    parser = subparsers.add_parser(
        "demo",
        help="Show the token before/after on this repo — the 30-second aha.",
        description=(
            "Measure, on your own project, what an agent reads with vs without "
            "OpenContext for a real task.\n\n"
            "  opencontext demo\n"
            '  opencontext demo --query "add rate limiting to the API"\n'
        ),
    )
    parser.add_argument("path", nargs="?", default=".", help="Project root (default: .).")
    parser.add_argument("--query", default=_DEFAULT_QUERY, help="The task to build context for.")


def handle_demo(runtime: Any, args: Any) -> int:
    """Render the before/after demo. Returns a process exit code."""
    root = Path(args.path)
    if not root.exists():
        console.print(f"[red]Not a directory:[/] {root}")
        return 1

    console.print("\n[bold]OpenContext demo[/]")
    try:
        manifest = runtime.load_manifest()
        if not manifest or not manifest.files:
            raise ValueError("empty")
        console.print(f"[dim]Using existing index ({len(manifest.files)} files)…[/]")
    except Exception:
        console.print("[dim]Indexing the project… (run once, faster next time)[/]")
        runtime.index_project(root)

    naive = estimate_naive_tokens(root)
    pack = runtime.build_context_pack(args.query)
    optimized = pack.used_tokens or 1
    files = list(pack.included)
    ratio = optimized / naive if naive else 1.0
    # Don't claim a saving that isn't there: on a tiny project the focused pack can
    # exceed a whole-project read, and the reduction only shows at real scale.
    if ratio < 1.0:
        delta_label = f"[bold]{min(99.9, round((1 - ratio) * 100, 1))}% less[/]"
    else:
        delta_label = "[dim]no reduction at this size — the win grows with the codebase[/]"

    console.print("\n[bold]Without OpenContext[/] — the agent reads the whole project:")
    console.print(f"   [red]{naive:,} tokens[/]")
    console.print(f"\n[bold]With OpenContext[/] — task: [italic]{args.query}[/]")
    console.print(f"   [green]{len(files)} files · {optimized:,} tokens[/]  ({delta_label})")

    if files:
        console.print("\n[dim]The files it chose, and why:[/]")
        for item in files[:8]:
            console.print(f"   [cyan]{item.source}[/]  [dim]{item.tokens:,} tok — {_why(item)}[/]")
        if len(files) > 8:
            console.print(f"   [dim]… and {len(files) - 8} more[/]")

    console.print(
        "\n[dim]That's the difference between an agent that skims everything and one "
        "that reads exactly what matters.[/]"
    )
    console.print('[dim]Try it on your own task:[/] opencontext explain "your task here"\n')

    import sys

    if sys.stdout.isatty():
        try:
            from opencontext_core import prompts

            if prompts.confirm("Set up this project now?", default=True):
                import argparse

                from opencontext_cli.main import _install

                _install(argparse.Namespace(root=str(root), yes=False))
        except (KeyboardInterrupt, EOFError):
            pass

    return 0
