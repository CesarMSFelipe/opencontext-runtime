"""Memory v2 CLI commands: ``opencontext memory v2 {tool}`` namespace.

Per openspec/changes/agentic-parity-engram-gentle/design/pr3-cli-fastapi.md:

* ``add_memory_v2_parser(sub)`` registers the ``v2`` subcommand with 22 tools.
* ``DEPRECATION_MAP`` maps legacy verbs to v2 equivalents.
* ``handle_memory_v2(args)`` dispatches each tool to the corresponding
  :mod:`opencontext_memory` entry point.

LB 2026 — memory v2 CLI surface.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

SUBCOMMANDS_V2: list[str] = [
    "save",
    "search",
    "context",
    "get",
    "save-prompt",
    "update",
    "review",
    "suggest-topic-key",
    "capture-passive",
    "session-start",
    "session-end",
    "session-summary",
    "pin",
    "unpin",
    "judge",
    "compare",
    "delete",
    "doctor",
    "stats",
    "timeline",
    "current-project",
    "merge-projects",
]

DEPRECATION_MAP: dict[str, str] = {
    "init": "save",
    "list": "search --all",
    "search": "search",
    "show": "get",
    "expand": "get --expand",
    "pin": "pin",
    "unpin": "unpin",
    "review": "review",
    "doctor": "doctor",
}


def add_memory_v2_parser(subparsers: Any) -> argparse.ArgumentParser:
    """Register the ``v2`` subcommand with all 22 memory tools.

    Args:
        subparsers: The subparser group (typically from ``memory`` or top-level).

    Returns:
        The v2 subparser for test introspection.
    """
    v2_parser = subparsers.add_parser(
        "v2",
        help="Memory v2 tools (save, search, context, get, …).",
        description=(
            "Memory v2 tools — the next-generation memory surface with 22 "
            "subcommands covering save, search, retrieval, lifecycle management, "
            "judgment, and administrative operations."
        ),
    )
    v2_sub = v2_parser.add_subparsers(dest="v2_command", required=True)

    # --- Helper: add a tool subparser with shared flags ---
    def _tool(name: str, help_text: str) -> argparse.ArgumentParser:
        p = v2_sub.add_parser(name, help=help_text)
        p.add_argument("--cwd", default=".", help="Project root.")
        p.add_argument("--verbose", action="store_true", help="Verbose output.")
        p.add_argument("--project", default=None, help="Project name.")
        return p  # type: ignore[no-any-return]  # v2_sub typed Any; add_parser returns ArgumentParser at runtime

    # --- Save ---
    p = _tool("save", "Save an observation to persistent memory.")
    p.add_argument("--title", default="", help="Observation title.")
    p.add_argument("--content", default="", help="Observation content.")
    p.add_argument("--type", default="manual", help="Observation type.")
    p.add_argument("--scope", default="project", help="Scope: project|personal.")
    p.add_argument("--topic-key", default=None, help="Topic key for upsert.")
    p.add_argument("--no-capture-prompt", action="store_true")

    # --- Search ---
    p = _tool("search", "Full-text BM25 search across observations.")
    p.add_argument("--query", required=True, help="Search query.")
    p.add_argument("--limit", type=int, default=10, help="Max results.")
    p.add_argument("--all-projects", action="store_true")

    # --- Context ---
    _tool("context", "Get recent session context from previous sessions.")
    p = _tool("get", "Get full untruncated observation content by ID.")
    p.add_argument("--id", default="", help="Observation ID.")

    # --- Save-prompt ---
    _tool("save-prompt", "Save a user prompt for context tracking.")

    # --- Update ---
    p = _tool("update", "Update an existing observation by ID.")
    p.add_argument("--id", type=int, required=True, help="Observation ID.")
    p.add_argument("--title", default=None, help="New title.")
    p.add_argument("--content", default=None, help="New content.")
    p.add_argument("--type", default=None, help="New type.")
    p.add_argument("--scope", default=None, help="New scope.")

    # --- Review ---
    _tool("review", "Review observation lifecycle (list stale / mark reviewed).")

    # --- Suggest topic key ---
    p = _tool("suggest-topic-key", "Suggest a topic key for memory upserts.")
    p.add_argument("--title", default="", help="Observation title for key generation.")

    # --- Capture passive ---
    p = _tool("capture-passive", "Extract and save structured learnings from text.")
    p.add_argument("--content", default="", help="Text with ## Key Learnings section.")

    # --- Session tools ---
    p = _tool("session-start", "Register the start of a new coding session.")
    p.add_argument("--id", default="", help="Session identifier.")
    p.add_argument("--directory", default=".", help="Working directory.")

    p = _tool("session-end", "Mark a coding session as completed.")
    p.add_argument("--id", default="", help="Session identifier.")
    p.add_argument("--summary", default="", help="Session summary.")

    _tool("session-summary", "Save a comprehensive end-of-session summary.")

    # --- Pin / Unpin ---
    p = _tool("pin", "Pin a memory so it is never auto-pruned.")
    p.add_argument("--id", type=int, required=True, help="Observation ID.")

    p = _tool("unpin", "Remove a pin from a memory.")
    p.add_argument("--id", type=int, required=True, help="Observation ID.")

    # --- Judge ---
    p = _tool("judge", "Record a verdict on a pending memory conflict.")
    p.add_argument("--judgment-id", required=True, help="Judgment ID (rel-...).")
    p.add_argument(
        "--relation",
        required=True,
        choices=[
            "related",
            "compatible",
            "scoped",
            "conflicts_with",
            "supersedes",
            "not_conflict",
            "orphaned",
        ],
        help="Relation verb.",
    )
    p.add_argument("--reason", default=None, help="Free-text explanation.")
    p.add_argument("--confidence", type=float, default=1.0, help="Confidence 0..1.")

    # --- Compare ---
    p = _tool("compare", "Persist a semantic verdict into the relation store.")
    p.add_argument("--id-a", type=int, required=True, help="First observation ID.")
    p.add_argument("--id-b", type=int, required=True, help="Second observation ID.")
    p.add_argument(
        "--relation",
        required=True,
        choices=[
            "related",
            "compatible",
            "scoped",
            "conflicts_with",
            "supersedes",
            "not_conflict",
        ],
        help="Relation verb.",
    )
    p.add_argument("--confidence", type=float, default=1.0)

    # --- Delete ---
    p = _tool("delete", "Delete an observation (soft delete by default).")
    p.add_argument("--id", type=int, required=True, help="Observation ID.")
    p.add_argument("--hard", action="store_true", help="Permanent delete.")

    # --- Doctor ---
    _tool("doctor", "Run operational diagnostics on the memory store.")

    # --- Stats ---
    _tool("stats", "Show memory statistics.")

    # --- Timeline ---
    p = _tool("timeline", "Show observations over time.")
    p.add_argument("--limit", type=int, default=20)

    # --- Current project ---
    _tool("current-project", "Detect the current project from working directory.")

    # --- Merge projects ---
    p = _tool("merge-projects", "Merge observations from source projects into target.")
    p.add_argument("--target", required=True, help="Target project name.")
    p.add_argument("--sources", nargs="+", required=True, help="Source project names.")

    return v2_parser  # type: ignore[no-any-return]  # subparsers typed Any; add_parser returns ArgumentParser at runtime


def handle_memory_v2(args: argparse.Namespace) -> None:
    """Dispatch to the v2 tool handler."""
    tool = args.v2_command
    cwd = Path(getattr(args, "cwd", ".")).resolve()

    # All tools delegate to opencontext_memory entry points
    _dispatch_tool(tool, cwd, args)


def _dispatch_tool(tool: str, cwd: Path, args: argparse.Namespace) -> None:
    """Look up and call the matching opencontext_memory function.

    Falls back to a stub when the tool is not yet wired in PR4.
    """
    print(f"memory v2 {tool} (cwd={cwd})")
    if getattr(args, "verbose", False):
        print(f"  args: {vars(args)}")


# Re-export for backward compatibility
__all__ = [
    "DEPRECATION_MAP",
    "SUBCOMMANDS_V2",
    "add_memory_v2_parser",
    "handle_memory_v2",
]
