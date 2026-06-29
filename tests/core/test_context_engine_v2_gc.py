"""PR-010 SPEC-CTX-010-13: incremental GC with triggers and book output format."""

from __future__ import annotations

from opencontext_core.context.gc import GcAttempt, GcTrigger, collect, compact_l1


def test_four_triggers_exist() -> None:
    assert {t.value for t in GcTrigger} == {
        "second_failed_diagnosis",
        "budget_exceeded",
        "workflow_transition",
        "consolidation",
    }


def test_second_failed_diagnosis_emits_book_output_format() -> None:
    l1 = {"diagnostics": "AssertionError in test_x", "scratch": "junk"}
    attempts = [
        GcAttempt(attempt=1, strategy="patch-import", reason="import was already correct"),
        GcAttempt(attempt=2, strategy="adjust-fixture", reason="fixture value was right"),
    ]
    compacted, output = collect(
        l1,
        GcTrigger.SECOND_FAILED_DIAGNOSIS,
        attempts,
        hypothesis="off-by-one in the loop bound",
    )
    lines = output.splitlines()
    assert lines[0] == "Attempt 1 failed because import was already correct."
    assert lines[1] == "Attempt 2 failed because fixture value was right."
    assert "Do not retry strategy patch-import." in lines
    assert "Do not retry strategy adjust-fixture." in lines
    assert lines[-1] == "Current verified hypothesis: off-by-one in the loop bound."
    # GC compacted L1: the transient scratch was dropped, diagnostics kept.
    assert "scratch" not in compacted
    assert compacted["diagnostics"] == "AssertionError in test_x"
    assert compacted["_gc"]["trigger"] == "second_failed_diagnosis"


def test_gc_output_is_redacted() -> None:
    attempts = [
        GcAttempt(attempt=1, strategy="s", reason="leaked AKIAIOSFODNN7EXAMPLE in config")
    ]
    _compacted, output = collect({}, GcTrigger.CONSOLIDATION, attempts)
    assert "AKIAIOSFODNN7EXAMPLE" not in output  # secret redacted via SinkGuard


def test_compact_l1_compresses_repeated_logs() -> None:
    l1 = {"logs": ["same"] * 50}
    compacted, discarded = compact_l1(l1)
    assert discarded == []
    assert len(compacted["logs"]) < 50  # repeated entries collapsed
