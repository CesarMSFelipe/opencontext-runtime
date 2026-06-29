"""Tests for the append-only event bus (SPEC RC-005)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.runtime.event_bus import CollectingConsumer, JsonlEventBus
from opencontext_core.runtime.events import make_event


def _event(session_id: str, type_: str) -> object:
    return make_event(session_id=session_id, type=type_, status="ok", message="m")


class TestAppendOnly:
    def test_publish_adds_one_line_and_preserves_prior_bytes(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        bus = JsonlEventBus(path)
        for i in range(3):
            bus.publish(_event("sess", f"session.created.{i}"))

        before_bytes = path.read_bytes()
        before_lines = path.read_text(encoding="utf-8").splitlines()
        assert len(before_lines) == 3

        bus.publish(_event("sess", "workflow.started"))

        after_lines = path.read_text(encoding="utf-8").splitlines()
        assert len(after_lines) == 4
        # The first N lines must be byte-identical to before the new append.
        assert path.read_bytes()[: len(before_bytes)] == before_bytes

    def test_never_truncates_on_reopen(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        JsonlEventBus(path).publish(_event("sess", "session.created"))
        # A fresh bus on the same path must append, not overwrite.
        JsonlEventBus(path).publish(_event("sess", "workflow.started"))
        assert len(path.read_text(encoding="utf-8").splitlines()) == 2


class TestSubscriberFanout:
    def test_consumer_receives_events_in_publish_order(self, tmp_path: Path) -> None:
        bus = JsonlEventBus(tmp_path / "events.jsonl")
        collector = CollectingConsumer()
        bus.subscribe(collector)

        bus.publish(_event("sess", "session.created"))
        bus.publish(_event("sess", "workflow.started"))
        bus.publish(_event("sess", "workflow.completed"))

        assert collector.types == [
            "session.created",
            "workflow.started",
            "workflow.completed",
        ]
