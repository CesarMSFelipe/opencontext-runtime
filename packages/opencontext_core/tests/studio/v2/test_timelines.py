"""REQ-studio-mvp-002: 11 event-family lanes (CONV2 #12)."""

from __future__ import annotations

from opencontext_studio.timelines import LANE_FAMILIES, render_timeline


def test_REQ_studio_mvp_002_eleven_lanes() -> None:
    assert len(LANE_FAMILIES) == 11
    assert "lifecycle" in LANE_FAMILIES
    assert "provider" in LANE_FAMILIES
    assert "plugin" in LANE_FAMILIES


def test_render_timeline_groups_events_by_family() -> None:
    events = [
        {"family": "lifecycle", "ts": "2026-07-01T00:00:00Z", "name": "start"},
        {"family": "provider", "ts": "2026-07-01T00:00:01Z", "name": "call"},
        {"family": "provider", "ts": "2026-07-01T00:00:02Z", "name": "fallback"},
    ]
    out = render_timeline(events)
    # All 11 lanes are returned; populated ones carry the events.
    assert set(out.keys()) == set(LANE_FAMILIES)
    assert out["lifecycle"] == [events[0]]
    assert len(out["provider"]) == 2
    assert out["benchmark"] == []
