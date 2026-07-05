"""Shared fixtures for opencontext_sdd tests.

PR1.a is library-only (no LLM, no network) but the guard is installed here
so future sub-PRs (PR1.b/c/d) inherit the mock-llm enforcement for free.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def fake_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.cwd()`` at ``tmp_path`` and chdir there.

    Use this when a test needs to call ``Resolve(change, cwd=...)`` and
    have the resolver read artifacts from an isolated directory. The
    ``cwd`` argument to ``Resolve`` is explicit, so this fixture is mostly
    a convenience for code that uses ``Path.cwd()`` indirectly.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _enforce_no_real_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Future-proof: no real LLM API calls ever escape from opencontext_sdd tests.

    PR1.a has no LLM dependency, but the guard is installed so sub-PRs
    inherit it. If any test (or production code) tries to read one of the
    known LLM env vars when ``mock/mock-llm`` should be active, the test
    fails fast.
    """
    # Allow the explicit mock-llm sentinel; ban any other provider.
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        existing = os.environ.get(var)
        if existing and existing != "mock/mock-llm":
            pytest.fail(
                f"Real LLM env var {var} is set during an opencontext_sdd test. "
                "Use mock/mock-llm or unset the variable."
            )
