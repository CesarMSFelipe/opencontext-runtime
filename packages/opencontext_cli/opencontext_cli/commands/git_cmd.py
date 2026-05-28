"""Git context CLI commands."""

from __future__ import annotations

import json
from typing import Any

from opencontext_core.dx.console_styles import console
from opencontext_core.indexing.git_context import GitContextProvider


def add_git_parser(subparsers: Any) -> None:
    """Add git command parsers."""
    import argparse
    git_parser = subparsers.add_parser("git", help=argparse.SUPPRESS)
    git_sub = git_parser.add_subparsers(dest="git_command", required=True)
    git_sub.add_parser("status", help="Show git repository stats.")
    git_history = git_sub.add_parser("history", help="Show git history for a file.")
    git_history.add_argument("file", help="File path.")
    git_history.add_argument("--json", action="store_true")
    git_recent = git_sub.add_parser("recent", help="Show recent changes.")
    git_recent.add_argument("--days", type=int, default=7)
    git_recent.add_argument("--max-commits", type=int, default=20)
    git_recent.add_argument("--json", action="store_true")
    git_blame = git_sub.add_parser("blame", help="Show blame for file lines.")
    git_blame.add_argument("file", help="File path.")
    git_blame.add_argument("--start", type=int, default=1)
    git_blame.add_argument("--end", type=int, default=10)
    git_blame.add_argument("--json", action="store_true")


def handle_git(args: Any) -> None:
    """Handle git commands."""
    command = args.git_command
    file = getattr(args, "file", None)
    start = getattr(args, "start", 1)
    end = getattr(args, "end", 10)
    days = getattr(args, "days", 7)
    max_commits = getattr(args, "max_commits", 20)
    json_output = getattr(args, "json", False)

    provider = GitContextProvider()
    if not provider.available:
        console.error("Not a git repository")
        return

    if command == "status":
        stats = provider.get_repo_stats()
        if json_output:
            print(json.dumps(stats, indent=2))
        else:
            console.header("Git Repository Stats")
            console.print(_format_git_status(stats))
    elif command == "history" and file:
        info = provider.get_file_info(file)
        if info:
            if json_output:
                data = {
                    "path": info.path,
                    "last_modified": info.last_modified.isoformat() if info.last_modified else None,
                    "last_author": info.last_author,
                    "commit_count": info.commit_count,
                    "lines_added": info.lines_added,
                    "lines_removed": info.lines_removed,
                    "top_authors": info.top_authors,
                }
                print(json.dumps(data, indent=2))
            else:
                console.header(f"Git History: {file}")
                console.print(_format_git_history(info))
        else:
            console.error(f"Could not get history for {file}")
    elif command == "recent":
        diffs = provider.get_recent_changes(days=days, max_commits=max_commits)
        if json_output:
            data = [
                {
                    "commit_hash": d.commit_hash,
                    "author": d.author,
                    "date": d.date.isoformat(),
                    "message": d.message,
                    "files_changed": d.files_changed,
                }
                for d in diffs
            ]
            print(json.dumps(data, indent=2))
        else:
            console.header(f"Recent Changes (last {days} days)")
            console.print(_format_git_recent(diffs))
    elif command == "blame" and file:
        lines = provider.get_blame_for_symbol(file, start, end)
        if json_output:
            print(json.dumps(lines, indent=2))
        else:
            console.header(f"Blame: {file} (lines {start}-{end})")
            console.print(_format_git_blame(lines))
    else:
        console.error(f"Unknown git command: {command}")


def _format_git_status(stats: dict[str, Any]) -> str:
    if not stats.get("available"):
        return "Not a git repository."
    lines = [
        f"Commits: {stats.get('total_commits', 'N/A')}",
        f"Contributors: {stats.get('contributors', 'N/A')}",
        f"Branches: {stats.get('branches', 'N/A')}",
    ]
    return "\n".join(lines)


def _format_git_history(info: Any) -> str:
    lines = [
        f"File: {info.path}",
        f"Commits: {info.commit_count}",
        f"Last author: {info.last_author or 'N/A'}",
        f"Last modified: {info.last_modified.isoformat() if info.last_modified else 'N/A'}",
        f"Lines added/removed: +{info.lines_added}/-{info.lines_removed}",
        f"Top authors: {', '.join(info.top_authors) if info.top_authors else 'N/A'}",
    ]
    return "\n".join(lines)


def _format_git_recent(diffs: list[Any]) -> str:
    lines = []
    for d in diffs:
        lines.append(f"{d.commit_hash[:8]} {d.author} {d.date.isoformat()}")
        lines.append(f"  {d.message}")
        lines.append(f"  Files: {', '.join(d.files_changed[:5])}")
        lines.append("")
    return "\n".join(lines)


def _format_git_blame(lines: list[dict[str, Any]]) -> str:
    out = []
    for line in lines:
        author = line.get("author", "?")
        code = line.get("code", "")
        out.append(f"{author:20} {code}")
    return "\n".join(out)
