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
import json
import sys
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
    p.add_argument(
        "--include-proposed",
        action="store_true",
        help="Also surface proposed (unapproved) memories.",
    )

    # --- Context ---
    _tool("context", "Get recent session context from previous sessions.")
    p = _tool("get", "Get full untruncated observation content by ID.")
    p.add_argument("--id", default="", help="Observation ID.")

    # --- Save-prompt ---
    p = _tool("save-prompt", "Save a user prompt for context tracking.")
    p.add_argument("--content", default="", help="The user prompt text.")

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

    p = _tool("session-summary", "Save a comprehensive end-of-session summary.")
    p.add_argument("--id", default="", help="Session identifier.")
    p.add_argument("--goal", default="", help="Session goal summary.")

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
    p.add_argument("--reasoning", default="", help="Reasoning for the comparison.")

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


def _open_store(cwd: Path) -> Any:
    """Open (creating if needed) the local v2 store under the path resolver."""
    from opencontext_memory import MemoryStore

    from opencontext_core.paths import StorageMode, resolve_storage_path

    db_path = resolve_storage_path(cwd, StorageMode.local) / "memory_v2.db"
    return MemoryStore.open(db_path)


def _approval_required(cwd: Path) -> bool:
    """Resolve ``memory.approval_required`` from the project config (best-effort)."""
    try:
        from opencontext_core.config import load_config_or_defaults
        from opencontext_core.config_resolver import resolve_config_path

        config = load_config_or_defaults(resolve_config_path(cwd), auto_detect=False)
        return bool(getattr(getattr(config, "memory", None), "approval_required", False))
    except Exception:
        return False


def _dispatch_tool(tool: str, cwd: Path, args: argparse.Namespace) -> None:
    """Call the matching opencontext_memory entry point.

    Every tool is wired to the local SQLite store (via ``_open_store``) or
    dispatched as a pure function when the tool takes no store.

    Verbs without a backend implementation (``stats``, ``timeline``,
    ``merge-projects``) exit 2 with an honest message so the caller is never
    silently swallowed by a no-op.
    """
    # --- save ---
    if tool == "save":
        from opencontext_memory import mem_save

        try:
            receipt = mem_save(
                _open_store(cwd),
                session_id=f"cli-{cwd.name}",
                project=cwd.name,
                title=getattr(args, "title", ""),
                content=getattr(args, "content", ""),
                type=getattr(args, "type", "manual"),
                topic_key=getattr(args, "topic_key", None),
                capture_prompt=not getattr(args, "no_capture_prompt", False),
                proposed=_approval_required(cwd),
            )
        except ValueError as exc:
            print(f"memory v2 save: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(receipt.model_dump_json(indent=2))
        return

    # --- search ---
    if tool == "search":
        from opencontext_memory import mem_search

        project = None if getattr(args, "all_projects", False) else cwd.name
        rows = mem_search(
            _open_store(cwd),
            query=getattr(args, "query", ""),
            limit=getattr(args, "limit", 10),
            project=project,
            include_proposed=getattr(args, "include_proposed", False),
        )
        print(json.dumps(rows, indent=2, default=str))
        return

    # --- context ---
    if tool == "context":
        from opencontext_memory import mem_context

        project = getattr(args, "project", None) or cwd.name
        rows = mem_context(
            _open_store(cwd),
            project=project,
            scope="project",
            limit=20,
            all_projects=False,
        )
        print(json.dumps(rows, indent=2, default=str))
        return

    # --- get ---
    if tool == "get":
        from opencontext_memory import mem_get_observation
        from opencontext_memory.tools.mem_get_observation import MemoryNotFound

        try:
            obs_id = int(getattr(args, "id", 0))
            result = mem_get_observation(_open_store(cwd), observation_id=obs_id)
        except (MemoryNotFound, LookupError, ValueError) as exc:
            print(f"memory v2 get: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(json.dumps(result, indent=2, default=str))
        return

    # --- save-prompt ---
    if tool == "save-prompt":
        from opencontext_memory import mem_save_prompt

        try:
            receipt = mem_save_prompt(
                _open_store(cwd),
                session_id=f"cli-{cwd.name}",
                content=getattr(args, "content", ""),
                project=getattr(args, "project", None) or cwd.name,
            )
        except ValueError as exc:
            print(f"memory v2 save-prompt: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(receipt.model_dump_json(indent=2))
        return

    # --- update ---
    if tool == "update":
        from opencontext_memory import mem_update

        obs_id = int(getattr(args, "id", 0))
        fields: dict[str, Any] = {}
        for field in ("title", "content", "type", "scope"):
            val = getattr(args, field, None)
            if val is not None:
                fields[field] = val
        try:
            result = mem_update(_open_store(cwd), observation_id=obs_id, **fields)
        except (ValueError, LookupError) as exc:
            print(f"memory v2 update: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(json.dumps(result, indent=2, default=str))
        return

    # --- review ---
    if tool == "review":
        from opencontext_memory import mem_review

        review_result = mem_review(_open_store(cwd), action="list")
        if isinstance(review_result, list):
            print(
                json.dumps(
                    [r.model_dump() if hasattr(r, "model_dump") else r for r in review_result],
                    indent=2,
                    default=str,
                )
            )
        else:
            print(json.dumps(review_result, indent=2, default=str))
        return

    # --- suggest-topic-key (pure — no store) ---
    if tool == "suggest-topic-key":
        from opencontext_memory import mem_suggest_topic_key

        key = mem_suggest_topic_key(title=getattr(args, "title", ""))
        print(json.dumps({"key": key}, indent=2))
        return

    # --- capture-passive (pure — no store) ---
    if tool == "capture-passive":
        from opencontext_memory import mem_capture_passive

        bullets = mem_capture_passive(content=getattr(args, "content", ""))
        print(json.dumps(bullets, indent=2))
        return

    # --- session-start ---
    if tool == "session-start":
        from opencontext_memory import mem_session_start

        record = mem_session_start(
            _open_store(cwd),
            session_id=getattr(args, "id", None) or f"cli-{cwd.name}",
            directory=getattr(args, "directory", None) or str(cwd),
            project=getattr(args, "project", None) or cwd.name,
        )
        print(record.model_dump_json(indent=2))
        return

    # --- session-end ---
    if tool == "session-end":
        from opencontext_memory import mem_session_end

        raw_summary = getattr(args, "summary", None)
        summary = raw_summary if raw_summary else None
        try:
            record = mem_session_end(
                _open_store(cwd),
                session_id=getattr(args, "id", None) or f"cli-{cwd.name}",
                summary=summary,
            )
        except ValueError as exc:
            print(f"memory v2 session-end: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(record.model_dump_json(indent=2))
        return

    # --- session-summary ---
    if tool == "session-summary":
        from opencontext_memory import mem_session_summary

        try:
            summary_record = mem_session_summary(
                _open_store(cwd),
                session_id=getattr(args, "id", None) or f"cli-{cwd.name}",
                goal=getattr(args, "goal", "") or "",
                instructions="",
                discoveries=[],
                accomplished=[],
                next_steps=[],
                relevant_files=[],
            )
        except ValueError as exc:
            print(f"memory v2 session-summary: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(summary_record.model_dump_json(indent=2))
        return

    # --- pin ---
    if tool == "pin":
        from opencontext_memory import mem_pin
        from opencontext_memory.tools.mem_get_observation import MemoryNotFound

        try:
            result = mem_pin(_open_store(cwd), observation_id=int(getattr(args, "id", 0)))
        except (MemoryNotFound, LookupError) as exc:
            print(f"memory v2 pin: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(json.dumps(result, indent=2, default=str))
        return

    # --- unpin ---
    if tool == "unpin":
        from opencontext_memory import mem_unpin
        from opencontext_memory.tools.mem_get_observation import MemoryNotFound

        try:
            result = mem_unpin(_open_store(cwd), observation_id=int(getattr(args, "id", 0)))
        except (MemoryNotFound, LookupError) as exc:
            print(f"memory v2 unpin: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(json.dumps(result, indent=2, default=str))
        return

    # --- judge ---
    if tool == "judge":
        from opencontext_memory import mem_judge

        try:
            row = mem_judge(
                _open_store(cwd),
                judgment_id=getattr(args, "judgment_id", ""),
                relation=getattr(args, "relation", ""),
                confidence=getattr(args, "confidence", 1.0),
                reason=getattr(args, "reason", None),
            )
        except (ValueError, LookupError) as exc:
            print(f"memory v2 judge: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(row.model_dump_json(indent=2))
        return

    # --- compare ---
    if tool == "compare":
        from opencontext_memory import mem_compare

        try:
            compare_result = mem_compare(
                _open_store(cwd),
                memory_id_a=int(getattr(args, "id_a", 0)),
                memory_id_b=int(getattr(args, "id_b", 0)),
                relation=getattr(args, "relation", ""),
                confidence=getattr(args, "confidence", 1.0),
                reasoning=getattr(args, "reasoning", ""),
            )
        except ValueError as exc:
            print(f"memory v2 compare: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(compare_result.model_dump_json(indent=2))
        return

    # --- delete ---
    if tool == "delete":
        from opencontext_memory import mem_delete

        mem_delete(
            _open_store(cwd),
            observation_id=int(getattr(args, "id", 0)),
            hard=getattr(args, "hard", False),
        )
        print(json.dumps({"deleted": True}, indent=2))
        return

    # --- doctor ---
    if tool == "doctor":
        from opencontext_memory import mem_doctor

        report = mem_doctor(_open_store(cwd))
        print(report.model_dump_json(indent=2))
        return

    # --- current-project (no store — pure cwd detection) ---
    if tool == "current-project":
        from opencontext_memory import mem_current_project

        detection = mem_current_project(cwd=cwd)
        print(detection.model_dump_json(indent=2))
        return

    # --- backendless verbs: honest exit-2 ---
    print(
        f"memory v2 {tool}: backend not implemented — no '{tool}' tool in "
        "opencontext_memory. Use 'opencontext memory' or the Engram MCP tools.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def handle_memory_lifecycle(args: argparse.Namespace, command: str) -> None:
    """Top-level approval-lifecycle verbs: approve / reject / compact / purge.

    All four operate on the workspace's v2 observations store and print pure
    JSON (no branded header) so scripted callers can parse stdout directly.
    """
    cwd = Path(getattr(args, "cwd", ".")).resolve()

    if command in ("approve", "reject"):
        from opencontext_memory import mem_approve, mem_reject

        handler = mem_approve if command == "approve" else mem_reject
        try:
            result = handler(_open_store(cwd), observation_id=int(args.memory_id))
        except (LookupError, ValueError) as exc:
            print(f"memory {command}: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(json.dumps(result, indent=2, default=str))
        return

    if command == "compact":
        from opencontext_memory import mem_compact

        result = mem_compact(_open_store(cwd))
        print(json.dumps(result, indent=2, default=str))
        return

    if command == "purge":
        if not getattr(args, "yes", False):
            print(
                "memory purge: refusing without --yes — this deletes ALL managed "
                "memory state for the workspace.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        from opencontext_memory import MemoryStore, mem_purge

        from opencontext_core.paths import StorageMode, resolve_storage_path

        storage = resolve_storage_path(cwd, StorageMode.local)
        report: dict[str, Any] = {
            "purged": True,
            "observations_removed": 0,
            "relations_removed": 0,
            "sessions_removed": 0,
        }
        obs_db = storage / "memory_v2.db"
        if obs_db.is_file():
            store = MemoryStore.open(obs_db)
            report.update(mem_purge(store))
            store.close()
        # Remove the managed store files outright (uninstall-grade wipe).
        removed_files: list[str] = []
        for stem in ("memory_v2.db", "memory.db"):
            for suffix in ("", "-wal", "-shm"):
                candidate = storage / f"{stem}{suffix}"
                if candidate.is_file():
                    candidate.unlink()
                    removed_files.append(str(candidate))
        report["removed_files"] = removed_files
        print(json.dumps(report, indent=2, default=str))
        return

    raise SystemExit(f"unknown memory lifecycle command: {command}")


# Re-export for backward compatibility
__all__ = [
    "DEPRECATION_MAP",
    "SUBCOMMANDS_V2",
    "add_memory_v2_parser",
    "handle_memory_lifecycle",
    "handle_memory_v2",
]
