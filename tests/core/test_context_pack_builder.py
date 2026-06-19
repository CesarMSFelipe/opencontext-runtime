from __future__ import annotations

from opencontext_core.context.packing import ContextPackBuilder
from opencontext_core.models.context import ContextItem, ContextPriority


def _item(
    item_id: str,
    priority: ContextPriority,
    tokens: int,
    score: float,
    source_type: str = "file",
) -> ContextItem:
    return ContextItem(
        id=item_id,
        content=item_id,
        source=f"{item_id}.py",
        source_type=source_type,
        priority=priority,
        tokens=tokens,
        score=score,
    )


def test_context_pack_includes_required_context_and_enforces_budget() -> None:
    result = ContextPackBuilder().pack(
        [
            _item("required", ContextPriority.P1, 30, 0.7),
            _item("large-low-value", ContextPriority.P5, 100, 0.2),
            _item("supporting", ContextPriority.P2, 25, 0.8),
        ],
        available_tokens=60,
        required_priorities={ContextPriority.P0, ContextPriority.P1},
    )

    assert [item.id for item in result.included] == ["required", "supporting"]
    assert result.used_tokens == 55
    assert result.omissions[0].item_id == "large-low-value"
    assert result.omissions[0].reason == "item_exceeds_available_budget"


def test_non_required_item_compresses_to_fit_instead_of_omitting() -> None:
    """M1: compression-to-fit was gated to P0/P1; a large non-required item that
    overflows the remaining budget should compress in, not be dropped."""
    from opencontext_core.config import (
        CompressionStrategy,
        OpenContextConfig,
        default_config_data,
    )
    from opencontext_core.context.compression import CompressionEngine

    config = OpenContextConfig.model_validate(default_config_data())
    compression = config.context.compression.model_copy(
        update={
            "strategy": CompressionStrategy.SIGNATURE,
            "protected_spans": False,
            "adaptive": False,
        }
    )
    engine = CompressionEngine(compression)

    body = "\n".join(f"    total += {i}" for i in range(80))
    source = f"def compute():\n    total = 0\n{body}\n    return total\n"
    big = ContextItem(
        id="big",
        content=source,
        source="big.py",
        source_type="file",
        priority=ContextPriority.P3,
        tokens=50,
        score=0.8,
    )

    result = ContextPackBuilder().pack(
        [_item("required", ContextPriority.P1, 70, 0.9), big],
        available_tokens=100,  # required (70) fits; big (50) overflows the remainder
        required_priorities={ContextPriority.P0, ContextPriority.P1},
        compression_engine=engine,
    )

    assert "big" in [item.id for item in result.included]


def test_context_pack_value_per_token_ordering() -> None:
    result = ContextPackBuilder().pack(
        [
            _item("dense", ContextPriority.P2, 10, 0.7),
            _item("large", ContextPriority.P2, 100, 0.9),
            _item("priority", ContextPriority.P1, 10, 0.1),
        ],
        available_tokens=30,
    )

    assert [item.id for item in result.included] == ["priority", "dense"]
    assert result.omitted[0].metadata["context_pack"]["decision"] == "item_exceeds_available_budget"
