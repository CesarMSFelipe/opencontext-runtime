"""Cross-turn AICX delta: round-trip, savings, and base-mismatch safety."""

from __future__ import annotations

import pytest

from opencontext_core.context.bytecode.compiler import _compute_checksum
from opencontext_core.context.bytecode.delta import (
    DeltaBaseMismatchError,
    apply_delta,
    delta_savings_pct,
    diff_bytecode,
)
from opencontext_core.context.bytecode.models import (
    BytecodeInstruction,
    ContextBytecode,
)
from opencontext_core.context.bytecode.validator import AICXValidator


def _bc(request_id: str, dictionary: dict[str, str]) -> ContextBytecode:
    # Minimal valid bytecode: REQ + TRUST are required by the validator.
    instructions = [
        BytecodeInstruction(op="REQ", args=["risk:low"]),
        BytecodeInstruction(op="TRUST", args=["ok"]),
        *[BytecodeInstruction(op="EVID", args=[k]) for k in dictionary],
    ]
    checksum = _compute_checksum("AICX/1", dictionary, instructions)
    return ContextBytecode(
        request_id=request_id,
        dictionary=dictionary,
        instructions=instructions,
        checksum=checksum,
    )


def test_roundtrip_reconstructs_exact_bytecode() -> None:
    prev = _bc("r1", {"v1": "shared evidence body", "v2": "old body"})
    new = _bc("r2", {"v1": "shared evidence body", "v3": "fresh body"})

    rebuilt = apply_delta(prev, diff_bytecode(prev, new))

    assert rebuilt.dictionary == new.dictionary  # exact, not a superset
    assert rebuilt.instructions == new.instructions
    assert rebuilt.checksum == new.checksum
    # The reconstructed bytecode is still valid (checksum covers the dictionary).
    assert AICXValidator().validate(rebuilt).passed


def test_delta_omits_unchanged_values() -> None:
    prev = _bc("r1", {"v1": "A very long shared evidence body " * 5, "v2": "x"})
    new = _bc("r2", {"v1": "A very long shared evidence body " * 5, "v3": "y"})

    delta = diff_bytecode(prev, new)

    # The big shared value is not re-sent; only the new key's value is.
    assert "v1" not in delta.added_dictionary
    assert delta.added_dictionary == {"v3": "y"}
    assert delta.dict_keys == ["v1", "v3"]  # full key set still carried
    assert delta_savings_pct(prev, new) > 90.0


def test_apply_refuses_wrong_base() -> None:
    prev = _bc("r1", {"v1": "a"})
    other = _bc("rX", {"v1": "different"})
    new = _bc("r2", {"v1": "a", "v2": "b"})

    delta = diff_bytecode(prev, new)
    with pytest.raises(DeltaBaseMismatchError):
        apply_delta(other, delta)  # base checksum differs -> refuse


def test_savings_zero_when_nothing_shared() -> None:
    prev = _bc("r1", {"a": "1"})
    new = _bc("r2", {"b": "2", "c": "3"})
    assert delta_savings_pct(prev, new) == 0.0
