"""Deterministic memory-kind classifier + advisory tagging on write."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.memory.kind_classifier import classify_kind
from opencontext_core.memory_usability.memory_candidates import MemoryKind
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


@pytest.mark.parametrize(
    "text, expected",
    [
        ("The login call raised a ZeroDivisionError in the handler", MemoryKind.ERROR),
        ("Traceback shows the parser crashed on empty input", MemoryKind.ERROR),
        ("We decided to use SQLite instead of Postgres for the local store", MemoryKind.DECISION),
        ("decision: adopt reciprocal-rank fusion for hybrid search", MemoryKind.DECISION),
        ("The token must not be logged and secrets are never on disk", MemoryKind.CONSTRAINT),
        ("Verified that all tests pass after the migration", MemoryKind.VALIDATION),
        ("In summary, the runtime plans, verifies, and remembers context", MemoryKind.SUMMARY),
        ("The auth module lives in src/auth.py", MemoryKind.FACT),
        ("too short", MemoryKind.FACT),  # below the word gate
    ],
)
def test_classify_kind(text: str, expected: MemoryKind) -> None:
    assert classify_kind(text) == expected


def test_classify_kind_is_deterministic() -> None:
    text = "We decided to use a deterministic classifier raised by the design review"
    assert classify_kind(text) == classify_kind(text)


def _record(content: str, tags: list[str] | None = None) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id="r1",
        layer=MemoryLayer.SEMANTIC,
        key="k:1",
        content=content,
        confidence=0.9,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=False),
        tags=tags or [],
        linked_nodes=[],
        created_at=now,
        updated_at=now,
    )


def test_write_adds_kind_tag_when_absent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalMemoryStore(Path(tmp) / "mem.db")
        store.write(_record("We decided to ship the new ranker this week"))
        recs = store._backend.get_by_key("k:1")
        assert any("kind:decision" in r.tags for r in recs)


def test_write_preserves_caller_kind_tag() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalMemoryStore(Path(tmp) / "mem.db")
        # Caller already tagged it; the classifier must not override.
        store.write(_record("We decided to ship the ranker", tags=["kind:fact"]))
        recs = store._backend.get_by_key("k:1")
        tags = [t for r in recs for t in r.tags if t.startswith("kind:")]
        assert tags == ["kind:fact"]
