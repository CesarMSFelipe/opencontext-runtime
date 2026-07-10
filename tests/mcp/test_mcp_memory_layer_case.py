"""F2: ``opencontext_memory_save`` must accept the UPPERCASE layer names its
own injected docs / context-pack tell agents to use.

The layer taxonomy is spelled lowercase in ``MemoryLayer`` (``semantic``,
``episodic``, ``failure`` ...), but the agent-facing instructions list the
layers UPPERCASE (SEMANTIC / EPISODIC / FAILURE). An agent that copies the
documented spelling used to get ``invalid layer 'SEMANTIC'`` and its save was
dropped. The fix normalizes the incoming ``layer`` case-insensitively before
validation; genuinely-unknown layers still raise.
"""

from __future__ import annotations

import pytest

from opencontext_core.mcp_stdio import _make_memory_record


@pytest.mark.parametrize(
    "supplied",
    ["SEMANTIC", "Semantic", "semantic", "  SEMANTIC  "],
    ids=["upper", "title", "lower", "padded"],
)
def test_layer_is_normalized_case_insensitively(supplied: str) -> None:
    """SEMANTIC / Semantic / semantic all resolve to the semantic layer."""
    record = _make_memory_record({"content": "durable fact", "layer": supplied})
    assert record.layer.value == "semantic"


def test_uppercase_failure_layer_resolves() -> None:
    """A second layer to prove the fix is general, not special-cased to semantic."""
    record = _make_memory_record({"content": "flaky", "layer": "FAILURE"})
    assert record.layer.value == "failure"


def test_genuinely_unknown_layer_still_rejected() -> None:
    """The normalization does not swallow real typos — banana still fails."""
    with pytest.raises(ValueError, match="invalid layer"):
        _make_memory_record({"content": "x", "layer": "banana"})


def test_missing_layer_defaults_to_episodic() -> None:
    """No regression: an omitted layer still defaults to episodic."""
    record = _make_memory_record({"content": "x"})
    assert record.layer.value == "episodic"
