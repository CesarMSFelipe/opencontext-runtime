"""The TDD posture reaches the harness apply code-gen context (Rodaja 5 A).

Both spines already ENFORCE the TDD gate, but the code model never learned the
posture — so under strict TDD it did not know it must write/keep a failing test
first. ``agents.executor`` now builds a single short TDD line from ``tdd_mode``
(and an optional ``red_proven`` flag) and composes it into the apply prompt
ALONGSIDE the minimal-diff signal + verified pack + task.

- ``strict`` → a failing test must drive the change; the RED-proven flag picks
  the "write minimal code to pass" vs "write the failing test first" half.
- ``ask`` / ``off`` → no TDD line.

Model-free: a capturing gateway records the prompt so we assert on it directly.
"""

from __future__ import annotations

from typing import Any

from opencontext_core.agents.executor import (
    MINIMAL_DIFF_SENTINEL,
    generate_apply_edits,
    tdd_codegen_note,
)

_TDD_SENTINEL = "TDD strict"


class _CapturingGateway:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def generate(self, request: Any) -> Any:
        self.calls.append(request)

        class _Resp:
            content = "[]"

        return _Resp()


# --------------------------------------------------------------------------- #
# tdd_codegen_note: the builder in isolation.
# --------------------------------------------------------------------------- #


def test_note_empty_for_ask_and_off() -> None:
    assert tdd_codegen_note("off") == ""
    assert tdd_codegen_note("off", red_proven=True) == ""
    # "ask": at most a single neutral note, never the strict directive.
    assert "TDD strict" not in tdd_codegen_note("ask")


def test_note_strict_without_red_proven_asks_for_failing_test_first() -> None:
    note = tdd_codegen_note("strict")
    assert _TDD_SENTINEL in note
    lowered = note.lower()
    assert "failing test" in lowered
    # Undetermined RED → the model is told to write the failing test first.
    assert "first" in lowered


def test_note_strict_with_red_proven_asks_for_minimal_code() -> None:
    note = tdd_codegen_note("strict", red_proven=True)
    assert _TDD_SENTINEL in note
    lowered = note.lower()
    # RED already proven → make it pass with the minimal code.
    assert "make it pass" in lowered or "minimal code" in lowered


# --------------------------------------------------------------------------- #
# generate_apply_edits: the posture reaches the apply prompt, additively.
# --------------------------------------------------------------------------- #


def test_apply_codegen_strict_carries_tdd_line() -> None:
    gateway = _CapturingGateway()
    context = {"task": "add a flag", "context": "PACK", "tdd_mode": "strict"}

    generate_apply_edits(gateway, context, provider="anthropic", model="claude")

    prompt = gateway.calls[0].prompt
    assert _TDD_SENTINEL in prompt
    # Additive: the minimal-diff signal + task survive alongside the TDD line.
    assert MINIMAL_DIFF_SENTINEL in prompt
    assert "add a flag" in prompt


def test_apply_codegen_off_omits_tdd_line() -> None:
    gateway = _CapturingGateway()
    context = {"task": "add a flag", "context": "PACK", "tdd_mode": "off"}

    generate_apply_edits(gateway, context, provider="anthropic", model="claude")

    prompt = gateway.calls[0].prompt
    assert _TDD_SENTINEL not in prompt
    # The rest of the composed prompt is unaffected.
    assert MINIMAL_DIFF_SENTINEL in prompt


def test_apply_codegen_absent_tdd_mode_omits_tdd_line() -> None:
    """No tdd_mode key at all → no TDD line (back-compat with callers pre-Rodaja 5)."""
    gateway = _CapturingGateway()
    context = {"task": "add a flag", "context": "PACK"}

    generate_apply_edits(gateway, context, provider="anthropic", model="claude")

    prompt = gateway.calls[0].prompt
    assert _TDD_SENTINEL not in prompt


def test_apply_codegen_strict_red_proven_picks_minimal_code_half() -> None:
    gateway = _CapturingGateway()
    context = {
        "task": "add a flag",
        "context": "PACK",
        "tdd_mode": "strict",
        "tdd_red_proven": True,
    }

    generate_apply_edits(gateway, context, provider="anthropic", model="claude")

    prompt = gateway.calls[0].prompt.lower()
    assert "make it pass" in prompt or "minimal code" in prompt
