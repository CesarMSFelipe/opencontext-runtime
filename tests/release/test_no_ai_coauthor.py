"""Release test: no Co-Authored-By trailers in recent commits.

Per openspec/changes/agentic-parity-engram-gentle/specs/general-agent-surface
§R6 — commit messages must not include Co-Authored-By trailers.

This test matches the trailer format only (``^Co-Authored-By: \\s+``).
Commit messages that reference the phrase as a concept (e.g. a subject
line describing the trailer-detection fix) are not trailers and are
not flagged.
"""

from __future__ import annotations

import re
import subprocess


_TRAILER_RE = re.compile(r"(?m)^Co-Authored-By:\s+")


class TestNoAiCoauthor:
    """Verify the last 50 commits have no ``Co-Authored-By`` trailers."""

    def test_no_coauthored_by_in_last_50_commits(self) -> None:
        result = subprocess.run(
            ["git", "log", "-50", "--format=%B%n---"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, "git log failed"
        for i, msg in enumerate(result.stdout.split("\n---\n")):
            matches = _TRAILER_RE.findall(msg)
            if matches:
                offenders = [
                    ln for ln in msg.splitlines() if _TRAILER_RE.search(ln)
                ]
                raise AssertionError(
                    f"Commit {i + 1} has Co-Authored-By trailer(s): {offenders}"
                )
