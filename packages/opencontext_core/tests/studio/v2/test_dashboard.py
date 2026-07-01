"""REQ-studio-mvp-004: 10-field session dashboard."""

from __future__ import annotations

from opencontext_studio.dashboard import render_dashboard, DASHBOARD_FIELDS


def test_REQ_studio_mvp_004_ten_fields() -> None:
    assert len(DASHBOARD_FIELDS) == 10


def test_render_dashboard_shape() -> None:
    session = {
        "session_id": "sess_test",
        "run_id": "run_test",
        "workflow": "explore",
        "started_at": "2026-07-01T00:00:00Z",
        "elapsed_ms": 1200,
        "ok": True,
        "warnings": 0,
        "errors": 0,
        "artifacts": ["a.json"],
        "decisions": 3,
    }
    out = render_dashboard(session)
    for f in DASHBOARD_FIELDS:
        assert f in out
    assert out["session_id"] == "sess_test"