"""Tests for the navigable-prompt helpers and their degradation path.

The interactive arrow-key path (InquirerPy) is exercised separately through a
pseudo-terminal; here we lock down the contract every caller relies on: choice
normalization, separator handling, and the non-TTY fallback that keeps CI and
piped runs from hanging or crashing.
"""

from __future__ import annotations

import pytest

from opencontext_core import prompts


@pytest.fixture
def no_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the non-interactive branch regardless of how tests are launched."""
    monkeypatch.setattr(prompts, "_is_tty", lambda: False)


# ── normalization ────────────────────────────────────────────────────────


def test_normalize_accepts_str_tuple_and_mapping() -> None:
    pairs = prompts._normalize(["x", ("y", "Y label"), {"value": "z", "name": "Z label"}])
    assert pairs == [("x", "x"), ("y", "Y label"), ("z", "Z label")]


def test_separator_is_non_selectable() -> None:
    pairs = prompts._normalize([prompts.SEPARATOR, ("a", "A"), prompts.SEPARATOR, ("b", "B")])
    assert prompts._selectable(pairs) == [("a", "A"), ("b", "B")]


# ── select ───────────────────────────────────────────────────────────────


def test_select_non_tty_returns_explicit_default(no_tty: None) -> None:
    assert prompts.select("m", [("a", "A"), ("b", "B")], default="b") == "b"


def test_select_non_tty_defaults_to_first_selectable(no_tty: None) -> None:
    # Leading separator must be skipped when deriving the implicit default.
    assert prompts.select("m", [prompts.SEPARATOR, ("a", "A"), ("b", "B")]) == "a"


def test_select_requires_a_selectable_choice(no_tty: None) -> None:
    with pytest.raises(ValueError):
        prompts.select("m", [prompts.SEPARATOR])


# ── checkbox (multi-select) ──────────────────────────────────────────────


def test_checkbox_non_tty_returns_defaults(no_tty: None) -> None:
    assert prompts.checkbox("m", [("a", "A"), ("b", "B")], defaults=["b"]) == ["b"]


def test_checkbox_non_tty_empty_when_no_defaults(no_tty: None) -> None:
    assert prompts.checkbox("m", [("a", "A"), ("b", "B")]) == []


# ── int_input ────────────────────────────────────────────────────────────


def test_int_input_non_tty_returns_default(no_tty: None) -> None:
    assert prompts.int_input("budget", default=3000) == 3000


def test_int_input_non_tty_clamps_default_to_bounds(no_tty: None) -> None:
    assert prompts.int_input("n", default=0, min_value=10) == 10
    assert prompts.int_input("n", default=99, max_value=50) == 50
    assert prompts.int_input("n", default=25, min_value=10, max_value=50) == 25


def test_int_input_tty_fallback_clamps_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    # A TTY without InquirerPy degrades to the rich integer prompt; answers
    # outside the [min, max] window are clamped instead of crashing the wizard.
    import rich.prompt

    monkeypatch.setattr(prompts, "_is_tty", lambda: True)
    monkeypatch.setattr(prompts, "_inquirer", lambda: None)
    monkeypatch.setattr(rich.prompt.IntPrompt, "ask", lambda *a, **k: 5)
    assert prompts.int_input("n", default=20, min_value=10, max_value=100) == 10
    monkeypatch.setattr(rich.prompt.IntPrompt, "ask", lambda *a, **k: 500)
    assert prompts.int_input("n", default=20, min_value=10, max_value=100) == 100


# ── confirm / text / secret / pause ──────────────────────────────────────


def test_confirm_non_tty_returns_default(no_tty: None) -> None:
    assert prompts.confirm("ok?", default=False) is False
    assert prompts.confirm("ok?", default=True) is True


def test_text_non_tty_returns_default(no_tty: None) -> None:
    assert prompts.text("name", default="x") == "x"


def test_secret_non_tty_returns_empty(no_tty: None) -> None:
    assert prompts.secret("key") == ""


def test_pause_non_tty_is_noop(no_tty: None) -> None:
    # Must return immediately without reading stdin.
    prompts.pause("press enter")
