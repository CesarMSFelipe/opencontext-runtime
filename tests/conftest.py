"""Shared test safeguards.

Some tests configure agents or run installers that write instruction files
(AGENTS.md, CLAUDE.md, ...) relative to the working directory. This guard ensures
no test can leave a write in the repository's own root files: it snapshots them
around every test and restores any that changed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GUARDED = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "QWEN.md", "opencontext.yaml")
_LOG = os.environ.get("OPENCONTEXT_POLLUTION_LOG")


@pytest.fixture(autouse=True)
def _protect_repo_root_files(request: pytest.FixtureRequest):
    before = {
        name: (path.read_text(encoding="utf-8") if (path := _REPO_ROOT / name).exists() else None)
        for name in _GUARDED
    }
    yield
    for name, prior in before.items():
        path = _REPO_ROOT / name
        now = path.read_text(encoding="utf-8") if path.exists() else None
        if now == prior:
            continue
        if prior is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(prior, encoding="utf-8")
        if _LOG:
            with open(_LOG, "a", encoding="utf-8") as handle:
                handle.write(f"{request.node.nodeid} -> {name}\n")
