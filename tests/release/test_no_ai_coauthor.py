"""Release test: no Co-Authored-By trailers in recent commits.

Per openspec/changes/agentic-parity-engram-gentle/specs/general-agent-surface
§R6 — commit messages must not include Co-Authored-By trailers.
"""

from __future__ import annotations

import subprocess


class TestNoAiCoauthor:
    """Verify the last 50 commits have no ``Co-Authored-By`` lines."""

    def test_no_coauthored_by_in_last_50_commits(self) -> None:
        result = subprocess.run(
            ["git", "log", "-50", "--format=%B%n---"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, "git log failed"
        for i, msg in enumerate(result.stdout.split("\n---\n")):
            if "Co-Authored-By:" in msg:
                lines = [l for l in msg.splitlines() if "Co-Authored-By" in l]
                raise AssertionError(
                    f"Commit {i+1} has Co-Authored-By trailer(s): {lines}"
                )
