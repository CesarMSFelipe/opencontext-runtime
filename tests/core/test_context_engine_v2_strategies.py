"""PR-010 SPEC-CTX-010-09: seven named retrieval strategies + dynamic selection."""

from __future__ import annotations

from opencontext_core.context.strategies import reorder, select_strategy
from opencontext_core.models.context import ContextItem, ContextPriority, RetrievalStrategy


def _item(
    item_id: str, source_type: str, *, symbol_kind: str = "", source: str = ""
) -> ContextItem:
    md = {"symbol_kind": symbol_kind} if symbol_kind else {}
    return ContextItem(
        id=item_id,
        content=item_id,
        source=source or f"{item_id}.py",
        source_type=source_type,
        priority=ContextPriority.P2,
        tokens=10,
        score=0.5,
        metadata=md,
    )


def test_all_seven_strategies_exist() -> None:
    assert {s.value for s in RetrievalStrategy} == {
        "symbol_first",
        "test_first",
        "owner_first",
        "failure_first",
        "architecture_first",
        "decision_first",
        "command_first",
    }


def test_selector_picks_failure_first_for_debug_node() -> None:
    assert select_strategy("diagnose", "") is RetrievalStrategy.FAILURE_FIRST
    assert select_strategy("apply", "debug the failing test") is RetrievalStrategy.FAILURE_FIRST


def test_selector_picks_test_first_for_verify_node() -> None:
    assert select_strategy("verify", "") is RetrievalStrategy.TEST_FIRST
    assert select_strategy("local_inspection", "") is RetrievalStrategy.TEST_FIRST


def test_selector_defaults_to_symbol_first() -> None:
    assert select_strategy("gather_context", "add a method") is RetrievalStrategy.SYMBOL_FIRST


def test_symbol_first_keeps_definition_above_test() -> None:
    items = [
        _item("test_foo", "file", source="tests/test_foo.py"),
        _item("Foo", "code", symbol_kind="class"),
        _item("readme", "file"),
    ]
    ordered = reorder(items, RetrievalStrategy.SYMBOL_FIRST)
    assert ordered[0].id == "Foo"  # the defining symbol leads, not its test


def test_failure_first_reorders_toward_diagnostics() -> None:
    items = [
        _item("util", "file"),
        ContextItem(
            id="trace",
            content="Traceback (most recent call last): ValueError",
            source="run.log",
            source_type="file",
            priority=ContextPriority.P2,
            tokens=10,
            score=0.4,
        ),
    ]
    ordered = reorder(items, RetrievalStrategy.FAILURE_FIRST)
    assert ordered[0].id == "trace"


def test_reorder_is_stable_within_bands() -> None:
    items = [_item(f"f{i}", "file") for i in range(5)]
    # No item matches symbol_first definition predicate strongly equal -> order preserved.
    ordered = reorder(items, RetrievalStrategy.OWNER_FIRST)
    assert [i.id for i in ordered] == [i.id for i in items]
