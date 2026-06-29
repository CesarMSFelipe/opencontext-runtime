"""Intelligence events + canonical telemetry layout + OTel exporter (SPEC-RI-011-17)."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.runtime_intelligence import events as ri_events
from opencontext_core.runtime_intelligence import telemetry_layout
from opencontext_core.runtime_intelligence.cost import CostEngine


def test_cost_report_emits_event_to_canonical_layout(tmp_path: Path, make_trace) -> None:
    engine = CostEngine()
    estimate = engine.estimate("fix bug", root=tmp_path)
    engine.report(
        session_id="s",
        run_id="r1",
        estimate=estimate,
        trace=make_trace(),
        root=tmp_path,
        emit=True,
    )
    events_path = tmp_path / telemetry_layout.TELEMETRY_DIR / telemetry_layout.EVENTS_FILE
    assert events_path.exists()
    events = telemetry_layout.read_events(tmp_path)
    assert any(e["event"] == ri_events.COST_REPORTED for e in events)
    assert all(
        e["family"] == "runtime_intelligence"
        for e in events
        if e["event"].startswith("intelligence.")
    )


def test_required_events_and_receipts_defined() -> None:
    assert len(ri_events.INTELLIGENCE_EVENTS) == 9
    assert ri_events.COST_REPORTED in ri_events.INTELLIGENCE_EVENTS
    assert ri_events.RECEIPT_WORKFLOW_COMPARISON in ri_events.INTELLIGENCE_RECEIPTS


def test_savings_telemetry_writes_only_canonical_ledger(tmp_path: Path) -> None:
    from opencontext_core.evaluation.telemetry import (
        TelemetryEvent,
        load_telemetry,
        record_event,
    )

    record_event(
        TelemetryEvent(
            timestamp=1.0,
            task="t",
            naive_tokens=1000,
            optimized_tokens=200,
            reduction_pct=80.0,
        ),
        root=tmp_path,
    )
    # The savings store round-trips through the canonical events ledger ...
    store = load_telemetry(tmp_path)
    assert store.total_saved == 800
    events = telemetry_layout.read_events(tmp_path)
    assert any(e["event"] == "telemetry.savings.recorded" for e in events)
    # ... and the legacy duplicate single file is NO LONGER written (footprint).
    assert not (tmp_path / telemetry_layout.LEGACY_TELEMETRY_FILE).exists()


def test_legacy_single_file_telemetry_still_readable(tmp_path: Path) -> None:
    """Pre-canonical projects (only telemetry.json) are read via the fallback."""
    import json as _json

    from opencontext_core.evaluation.telemetry import load_telemetry

    legacy_path = tmp_path / telemetry_layout.LEGACY_TELEMETRY_FILE
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        _json.dumps(
            {
                "events": [
                    {
                        "timestamp": 1.0,
                        "task": "t",
                        "naive_tokens": 1000,
                        "optimized_tokens": 200,
                        "reduction_pct": 80.0,
                        "scenario": "",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    # The legacy shim reads it ...
    legacy = telemetry_layout.read_legacy_telemetry(tmp_path)
    assert legacy and legacy[0]["naive_tokens"] == 1000
    # ... and load_telemetry falls back to it when no canonical ledger exists.
    store = load_telemetry(tmp_path)
    assert store.total_saved == 800


def test_otel_exporter_off_by_default(tmp_path: Path, make_trace) -> None:
    assert telemetry_layout.export_otel([make_trace()], root=tmp_path) is None
    # Nothing was written when disabled.
    assert not (tmp_path / telemetry_layout.TELEMETRY_DIR / "otel-spans.json").exists()


def test_otel_exporter_when_enabled_writes_spans(tmp_path: Path, make_trace) -> None:
    path = telemetry_layout.export_otel([make_trace()], enabled=True, root=tmp_path)
    assert path is not None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data.get("spans")
