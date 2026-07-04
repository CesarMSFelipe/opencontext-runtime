"""Explain CLI — make the "verified, minimal context" promise visible.

`opencontext explain "<task>"` shows WHY each file is in the context pack (the
signal that selected it), what was kept out and why, and the token economics — so
the agent's context is auditable instead of a black box.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from opencontext_core.dx.console_styles import console


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
    parser.add_argument(
        "--breakdown",
        action="store_true",
        help="Show the per-signal score components for each included file.",
    )
    parser.add_argument(
        "--why",
        metavar="FILE",
        default=None,
        help="Explain why a single FILE is (or isn't) in the context.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON (CI-friendly).")


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


def _breakdown(item: Any) -> str:
    """The per-signal decision components for an item, from data already on it.

    Surfaces the score inputs the ranker recorded (priority, source trust,
    freshness, and the retrieval kind/node) — no pipeline call, just a readable
    view of the metadata the planner already attached to ``pack.included``.
    """
    md = getattr(item, "metadata", None) or {}
    parts: list[str] = []
    priority = getattr(item, "priority", None)
    priority_value = getattr(priority, "value", priority)
    if priority_value is not None:
        parts.append(f"priority={priority_value}")
    trust = getattr(item, "source_trust", None)
    if trust is not None:
        parts.append(f"trust={float(trust):.2f}")
    freshness = md.get("freshness")
    if freshness:
        parts.append(f"freshness={freshness}")
    retrieval = md.get("retrieval") or {}
    node, kind = retrieval.get("node"), retrieval.get("kind")
    if node and kind:
        parts.append(f"{kind}:{node}")
    fts_rank = retrieval.get("fts_rank")
    if fts_rank is not None:
        parts.append(f"fts_rank={fts_rank}")
    return " · ".join(parts) or "—"


def handle_explain(runtime: Any, args: Any) -> int:
    """Render the why-this-context view. Returns a process exit code."""
    root = Path(args.root)
    if args.root != "." and root.exists():
        runtime.index_project(root)

    pack = runtime.build_context_pack(args.query, args.max_tokens)
    included = list(pack.included)
    omitted = list(pack.omitted)
    reasons = {o.item_id: o.reason for o in pack.omissions}

    if getattr(args, "json", False):
        payload: dict[str, Any] = {
            "schema": "opencontext/explain/v1",
            "query": args.query,
            "used_tokens": pack.used_tokens,
            "included": [
                {
                    "source": it.source,
                    "score": float(it.score),
                    "tokens": it.tokens,
                    "why": _why(it),
                }
                for it in included
            ],
            "omitted": [
                {
                    "source": it.source,
                    "tokens": it.tokens,
                    "reason": reasons.get(it.id, "below the budget/diversity cut"),
                }
                for it in omitted
            ],
            "error": None,
        }
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    # --why FILE: a focused single-file rationale, not the full table.
    why_file = getattr(args, "why", None)
    if why_file:
        _render_why_file(why_file, included)
        freshness_nudge(runtime, root)
        return 0

    breakdown = bool(getattr(args, "breakdown", False))
    console.header("Why This Context")
    console.print(f"[italic]{args.query}[/]")
    redacted = sum(1 for it in included if getattr(it, "redacted", False))
    summary = f"{len(included)} files · {pack.used_tokens:,} tokens"
    if redacted:
        summary += f" · {redacted} with secrets redacted"
    console.dim(summary)

    if included:
        columns = ["File", "Score", "Tok"]
        if breakdown:
            columns.append("Signals")
        columns.append("Why")
        rows: list[list[str]] = []
        for item in included:
            row = [item.source, f"{item.score:.2f}", f"{item.tokens:,}"]
            if breakdown:
                row.append(_breakdown(item))
            row.append(_why(item))
            rows.append(row)
        console.table("Included", columns, rows)
    else:
        console.warning("No files selected for this task.")

    if omitted:
        console.dim("Kept out (and why):")
        for item in omitted:
            reason = reasons.get(item.id, "below the budget/diversity cut")
            console.dim(f"  ✗ {item.source}  {item.tokens:,} tok — {reason}")

    freshness_nudge(runtime, root)
    return 0


def _render_why_file(why_file: str, included: list[Any]) -> None:
    """Print the inclusion rationale for one file, or a clean 'not included'.

    Matches a file by exact source or basename so both ``src/auth.py`` and
    ``auth.py`` resolve. Reads only data already on ``pack.included`` (B3-REQ-2).
    """
    needle = why_file.strip()
    matches = [
        it for it in included if it.source == needle or Path(it.source).name == Path(needle).name
    ]
    console.header("Why This File")
    console.print(f"[italic]{needle}[/]")
    if not matches:
        console.warning(
            f"{needle} is not included in the context for this task "
            "(below the budget/diversity cut, or not retrieved)."
        )
        return
    for item in matches:
        console.print(f"[cyan]{item.source}[/]")
        console.print(
            f"  [green]score[/] {item.score:.2f} · [dim]{item.tokens:,} tok[/] · {_why(item)}"
        )
        console.dim(f"  signals: {_breakdown(item)}")


def freshness_nudge(runtime: Any, root: Path) -> None:
    """Warn if the index drifted from disk (stale context erodes trust). Best-effort."""
    try:
        report = runtime.knowledge_graph.stale_files(root)
    except Exception:
        return
    if report.total:
        console.warning(
            f"Index is {report.total} files behind the working tree — "
            "run `opencontext index .` for fresh context."
        )
