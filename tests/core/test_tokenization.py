"""Tests for the optional accurate tokenizer with heuristic fallback."""

from __future__ import annotations

import builtins
import importlib

import pytest

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.context.tokenization import (
    accurate_tokenizer_available,
    count_tokens,
)


def _tiktoken_installed() -> bool:
    try:
        import tiktoken  # noqa: F401
    except ImportError:
        return False
    return True


def test_empty_text_is_zero_tokens() -> None:
    assert count_tokens("") == 0
    assert count_tokens("   \n\t ") == 0


def test_count_tokens_is_deterministic() -> None:
    text = "def authenticate(user: str, password: str) -> bool:\n    return True\n"
    assert count_tokens(text) == count_tokens(text)


def test_count_tokens_matches_heuristic_when_tiktoken_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without tiktoken, count_tokens must equal the existing char/4 heuristic."""

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "tiktoken" or name.startswith("tiktoken."):
            raise ImportError("tiktoken disabled for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    module = importlib.import_module("opencontext_core.context.tokenization")
    importlib.reload(module)
    try:
        assert module.accurate_tokenizer_available() is False
        text = "authentication " * 40
        assert module.count_tokens(text) == estimate_tokens(text)
        assert module.count_tokens("hello world") == estimate_tokens("hello world")
    finally:
        # Restore the module to its real state for other tests.
        monkeypatch.undo()
        importlib.reload(module)


def test_count_tokens_plausible_when_tiktoken_present() -> None:
    if not _tiktoken_installed():
        pytest.skip("tiktoken is not installed in this environment")

    text = "The quick brown fox jumps over the lazy dog. " * 5
    accurate = count_tokens(text)
    # A plausible token count is positive and not absurdly larger than word count.
    assert accurate > 0
    word_count = len(text.split())
    assert accurate <= word_count * 3
    assert accurate_tokenizer_available() is True


def test_unknown_model_falls_back_without_raising() -> None:
    # An unknown model name must never raise; it falls back to a usable count.
    value = count_tokens("hello world", model="definitely-not-a-real-model-xyz")
    assert value > 0
