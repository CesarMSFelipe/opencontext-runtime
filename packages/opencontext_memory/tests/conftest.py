"""Shared fixtures for opencontext_memory tests.

PR2.a introduces the SQLite + FTS5 store and the cross-process write queue.
There is no LLM surface yet, but the autouse mock-llm guard is installed so
future tool modules (PR2.b/c/d) inherit the same enforcement for free.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def store_db(tmp_path: Path) -> Path:
    """Return an isolated sqlite path under ``tmp_path`` for the store fixture."""
    return tmp_path / "memory.sqlite3"


@pytest.fixture(autouse=True)
def _enforce_no_real_llm() -> None:
    """Ban any real LLM env var during opencontext_memory tests.

    The memory store is local-only and never reaches a provider. The guard is
    future-proof: if a future tool module (PR2.b+) accidentally reads a real
    provider key, the test fails fast with a clear remediation message.
    """
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        existing = os.environ.get(var)
        if existing and existing != "mock/mock-llm":
            pytest.fail(
                f"Real LLM env var {var} is set during an opencontext_memory test. "
                "Use mock/mock-llm or unset the variable."
            )
