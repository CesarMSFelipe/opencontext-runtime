"""Git-aware context enrichment for the knowledge graph.

Indexes git history, file changes, authorship, and diffs to provide
additional context when building AI task context or analyzing impact.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class GitFileInfo:
    """Git metadata for a single file."""

    path: str
    last_modified: datetime | None
    last_author: str | None
    commit_count: int
    lines_added: int
    lines_removed: int
    top_authors: list[str]


@dataclass
class GitDiff:
    """A parsed git diff."""

    commit_hash: str
    author: str
    date: datetime
    message: str
    files_changed: list[str]
    diff_text: str


class GitContextProvider:
    """Provides git context enrichment for knowledge graph operations.

    Integrates with the knowledge graph to add git-aware metadata
    to nodes and edges, enabling better context selection and impact analysis.
    """

    def __init__(self, repo_path: str | Path = ".") -> None:
        self.repo_path = Path(repo_path)
        self._available = self._check_git()

    def _check_git(self) -> bool:
        """Check if the repository is a git repo."""
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            return False
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo_path), "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    @property
    def available(self) -> bool:
        return self._available

    def get_file_info(self, file_path: str | Path) -> GitFileInfo | None:
        """Get git metadata for a file.

        Returns commit count, last author, and modification history.
        """
        if not self._available:
            return None

        path = Path(file_path)
        try:
            # Last modified date and author
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repo_path),
                    "log",
                    "-1",
                    "--format=%aI|%an",
                    "--",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            last_modified = None
            last_author = None
            if result.stdout.strip():
                parts = result.stdout.strip().split("|", 1)
                if len(parts) == 2:
                    last_modified = datetime.fromisoformat(parts[0])
                    last_author = parts[1]

            # Commit count
            count_result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repo_path),
                    "rev-list",
                    "--count",
                    "HEAD",
                    "--",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            commit_count = int(count_result.stdout.strip() or 0)

            # Lines added/removed
            stat_result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repo_path),
                    "log",
                    "--numstat",
                    "--format=",
                    "--",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            lines_added = 0
            lines_removed = 0
            for line in stat_result.stdout.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) >= 2:
                    try:
                        lines_added += int(parts[0]) if parts[0] != "-" else 0
                        lines_removed += int(parts[1]) if parts[1] != "-" else 0
                    except ValueError:
                        pass

            # Top authors
            authors_result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repo_path),
                    "log",
                    "--format=%an",
                    "--",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            authors: dict[str, int] = {}
            for author in authors_result.stdout.strip().split("\n"):
                if author:
                    authors[author] = authors.get(author, 0) + 1
            top_authors = sorted(authors, key=lambda a: authors[a], reverse=True)[:3]

            return GitFileInfo(
                path=str(path),
                last_modified=last_modified,
                last_author=last_author,
                commit_count=commit_count,
                lines_added=lines_added,
                lines_removed=lines_removed,
                top_authors=top_authors,
            )
        except (subprocess.SubprocessError, ValueError):
            return None

    def get_recent_changes(self, days: int = 7, max_commits: int = 20) -> list[GitDiff]:
        """Get recent git changes within the last N days."""
        if not self._available:
            return []

        try:
            datetime.now().isoformat()
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repo_path),
                    "log",
                    f"--since={days}.days ago",
                    f"--max-count={max_commits}",
                    "--format=%H|%an|%aI|%s",
                    "--name-only",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            diffs: list[GitDiff] = []
            current_diff: dict[str, Any] | None = None

            for line in result.stdout.strip().split("\n"):
                if "|" in line and not line.startswith(" "):
                    if current_diff:
                        diffs.append(GitDiff(**current_diff))
                    parts = line.split("|", 3)
                    current_diff = {
                        "commit_hash": parts[0],
                        "author": parts[1],
                        "date": datetime.fromisoformat(parts[2]),
                        "message": parts[3],
                        "files_changed": [],
                        "diff_text": "",
                    }
                elif line.strip() and current_diff is not None:
                    current_diff["files_changed"].append(line.strip())

            if current_diff:
                diffs.append(GitDiff(**current_diff))

            return diffs
        except (subprocess.SubprocessError, ValueError):
            return []

    def get_blame_for_symbol(
        self,
        file_path: str,
        line_start: int,
        line_end: int,
    ) -> list[dict[str, Any]]:
        """Get git blame for a range of lines in a file.

        Useful for understanding who last modified specific functions or classes.
        """
        if not self._available:
            return []

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repo_path),
                    "blame",
                    f"-L{line_start},{line_end}",
                    "--line-porcelain",
                    file_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            lines: list[dict[str, Any]] = []
            current: dict[str, Any] = {}

            for line in result.stdout.split("\n"):
                if line.startswith("author "):
                    current["author"] = line[7:]
                elif line.startswith("author-time "):
                    timestamp = int(line[12:])
                    current["date"] = datetime.fromtimestamp(timestamp)
                elif line.startswith("summary "):
                    current["message"] = line[8:]
                elif line.startswith("\t"):
                    current["code"] = line[1:]
                    lines.append(current)
                    current = {}

            return lines
        except (subprocess.SubprocessError, ValueError):
            return []

    def get_files_changed_in_last_commit(self) -> list[str]:
        """Get list of files changed in the most recent commit."""
        if not self._available:
            return []

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repo_path),
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    "HEAD",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return [f for f in result.stdout.strip().split("\n") if f]
        except subprocess.SubprocessError:
            return []

    def enrich_context(
        self,
        file_paths: list[str],
        include_git_history: bool = True,
    ) -> dict[str, Any]:
        """Enrich file context with git metadata.

        Returns a dict mapping file paths to their git info.
        """
        if not self._available or not include_git_history:
            return {}

        enriched: dict[str, Any] = {}
        for path in file_paths:
            info = self.get_file_info(path)
            if info:
                enriched[path] = {
                    "last_modified": info.last_modified.isoformat() if info.last_modified else None,
                    "last_author": info.last_author,
                    "commit_count": info.commit_count,
                    "top_authors": info.top_authors,
                }
        return enriched

    def get_repo_stats(self) -> dict[str, Any]:
        """Get overall repository git statistics."""
        if not self._available:
            return {"available": False}

        try:
            # Total commits
            commits_result = subprocess.run(
                ["git", "-C", str(self.repo_path), "rev-list", "--count", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            total_commits = int(commits_result.stdout.strip() or 0)

            # Contributors
            authors_result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.repo_path),
                    "log",
                    "--format=%an",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            contributors = len(set(authors_result.stdout.strip().split("\n")) - {""})

            # Branches
            branches_result = subprocess.run(
                ["git", "-C", str(self.repo_path), "branch", "-a"],
                capture_output=True,
                text=True,
                check=True,
            )
            branches = len([b for b in branches_result.stdout.strip().split("\n") if b.strip()])

            return {
                "available": True,
                "total_commits": total_commits,
                "contributors": contributors,
                "branches": branches,
            }
        except (subprocess.SubprocessError, ValueError):
            return {"available": True, "error": "failed to get stats"}
