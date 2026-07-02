"""Tests for the telemetry module (trace_id round-trip)."""

from __future__ import annotations

from opencontext_sdd.telemetry import (
    current_trace_id,
    emit_trace_id,
    with_trace_id,
)


def test_trace_id_round_trip() -> None:
    """emit_trace_id() → with_trace_id() → observable during context → restored after."""
    assert current_trace_id() is None
    tid = emit_trace_id()
    with with_trace_id(tid):
        assert current_trace_id() == tid
    assert current_trace_id() is None
