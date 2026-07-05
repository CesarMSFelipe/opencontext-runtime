"""Context pack truthfulness tests (PR-AHE-006).

Verifies that JSON packs emit honest budget metadata, record omissions when content
is skipped due to budget constraints, and emit compression metadata only when
compression actually ran.
"""

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
        content=item_id * 10,
        source=f"{item_id}.py",
        source_type=source_type,
        priority=priority,
        tokens=tokens,
        score=score,
    )


def test_pack_has_token_budget_and_used() -> None:
    """Packed result must expose token_budget and tokens_used on every pack."""
    budget = 100
    result = ContextPackBuilder().pack(
        [
            _item("a", ContextPriority.P1, 30, 0.9),
            _item("b", ContextPriority.P2, 25, 0.7),
        ],
        available_tokens=budget,
    )

    # token_budget is the alias for available_tokens (what was given to the packer).
    assert result.token_budget == budget, (
        f"token_budget must equal the budget given to the packer ({budget}), "
        f"got {result.token_budget}"
    )
    # tokens_used is the alias for used_tokens (what included items actually consumed).
    assert result.tokens_used == result.used_tokens, (
        "tokens_used property must equal used_tokens field"
    )
    assert result.tokens_used <= budget, "tokens_used must not exceed the budget"

    # Verify the same values appear in model_dump (JSON serialization).
    dumped = result.model_dump()
    assert dumped["available_tokens"] == budget
    assert dumped["used_tokens"] == result.used_tokens


def test_pack_omissions_recorded_under_budget() -> None:
    """When budget is too tight to fit all items, omissions must list the excluded items."""
    result = ContextPackBuilder().pack(
        [
            _item("fits", ContextPriority.P1, 30, 0.9),
            _item("too_large", ContextPriority.P5, 200, 0.2),
            _item("also_fits", ContextPriority.P2, 20, 0.6),
        ],
        available_tokens=60,
    )

    included_ids = {item.id for item in result.included}
    omission_ids = {o.item_id for o in result.omissions}

    assert "fits" in included_ids, "high-priority item should be included"
    assert "too_large" in omission_ids, "item exceeding total budget must appear in omissions"

    # Omissions must have a non-empty reason code.
    for omission in result.omissions:
        assert omission.reason, f"omission for {omission.item_id!r} has no reason"
        assert omission.tokens > 0, f"omission for {omission.item_id!r} has zero tokens"

    # Omissions must appear in model_dump (so JSON consumers can see what was dropped).
    dumped = result.model_dump()
    assert isinstance(dumped["omissions"], list)
    assert len(dumped["omissions"]) >= 1


def test_pack_compression_metadata_only_when_compressed() -> None:
    """Compression metadata must be absent when no compression ran, present when it did."""
    # Without a compression engine — no compression should be emitted.
    result_no_compression = ContextPackBuilder().pack(
        [
            _item("x", ContextPriority.P1, 40, 0.9),
            _item("y", ContextPriority.P2, 30, 0.6),
        ],
        available_tokens=80,
        compression_engine=None,
    )

    assert result_no_compression.compression is None, (
        "compression field must be absent (None) when no compression engine was used"
    )
    dumped_no_comp = result_no_compression.model_dump()
    assert dumped_no_comp["compression"] is None, (
        "compression key must be null in JSON when compression did not run"
    )

    # With a compression engine that actually fires — metadata must be present.
    from opencontext_core.config import (
        CompressionStrategy,
        OpenContextConfig,
        default_config_data,
    )
    from opencontext_core.context.compression import CompressionEngine

    config = OpenContextConfig.model_validate(default_config_data())
    compression_cfg = config.context.compression.model_copy(
        update={
            "strategy": CompressionStrategy.SIGNATURE,
            "protected_spans": False,
            "adaptive": False,
        }
    )
    engine = CompressionEngine(compression_cfg)

    # Craft items so one overflows the remaining budget and must be compressed to fit.
    body = "\n".join(f"    result += value_{i}" for i in range(60))
    large_content = f"def compute():\n    result = 0\n{body}\n    return result\n"
    large_item = ContextItem(
        id="large",
        content=large_content,
        source="large.py",
        source_type="file",
        priority=ContextPriority.P3,
        tokens=50,
        score=0.8,
    )
    small_item = _item("small", ContextPriority.P1, 70, 0.9)

    result_with_compression = ContextPackBuilder().pack(
        [small_item, large_item],
        available_tokens=100,
        compression_engine=engine,
    )

    # The large item should compress into the remaining 30 tokens.
    if any(i.id == "large" for i in result_with_compression.included):
        # Compression fired — metadata must be present and truthful.
        comp = result_with_compression.compression
        assert comp is not None, (
            "compression field must be present when at least one item was compressed"
        )
        assert comp.enabled is True
        assert comp.tokens_before > comp.tokens_after, (
            "tokens_before must exceed tokens_after when compression ran"
        )
        assert comp.items_compressed >= 1

        dumped_comp = result_with_compression.model_dump()
        assert dumped_comp["compression"] is not None
        assert dumped_comp["compression"]["enabled"] is True
        assert "tokens_before" in dumped_comp["compression"]
        assert "tokens_after" in dumped_comp["compression"]
    else:
        # Compression attempted but the item didn't fit even after compression;
        # the pack has no compression metadata because nothing was compressed-in.
        assert result_with_compression.compression is None, (
            "compression must be None when no item was actually compressed into the pack"
        )
