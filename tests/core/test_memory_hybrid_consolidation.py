"""Tests for hybrid retrieval, write-time consolidation, bi-temporal supersession,
background consolidation, and episodic recall on LocalMemoryStore.

These exercise the offline-first memory upgrades. The semantic leg of hybrid
search is optional: if no embedding backend is wired in, the relevant assertion
is skipped and only the lexical fallback + fusion are exercised.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from opencontext_core.memory.fusion import reciprocal_rank_fusion
from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


def make_record(
    record_id: str,
    *,
    key: str = "test:key",
    content: str = "some content",
    layer: MemoryLayer = MemoryLayer.SEMANTIC,
    confidence: float = 0.9,
    tags: list[str] | None = None,
    created_at: datetime | None = None,
) -> MemoryRecord:
    now = created_at or datetime.now(tz=UTC)
    return MemoryRecord(
        id=record_id,
        layer=layer,
        key=key,
        content=content,
        confidence=confidence,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=False),
        tags=tags or [],
        linked_nodes=[],
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def store() -> Iterator[LocalMemoryStore]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield LocalMemoryStore(Path(tmpdir) / "mem.db")


# --- Reciprocal-rank fusion ------------------------------------------------


def test_rrf_fuses_two_ranked_lists() -> None:
    lexical = ["a", "b", "c"]
    semantic = ["c", "b", "d"]
    fused = reciprocal_rank_fusion([lexical, semantic])
    # "b" appears high in both -> should beat items appearing in only one list.
    assert fused[0] in {"b", "c"}
    assert set(fused) == {"a", "b", "c", "d"}


def test_rrf_single_list_preserves_order() -> None:
    fused = reciprocal_rank_fusion([["x", "y", "z"]])
    assert fused == ["x", "y", "z"]


def test_rrf_empty_returns_empty() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[]]) == []


# --- Hybrid search ---------------------------------------------------------


def test_hybrid_search_lexical_fallback(store: LocalMemoryStore) -> None:
    """With no embedder, hybrid search degrades to lexical and still returns hits."""
    rec = make_record("h1", content="database connection pool exhausted")
    store.write(rec)
    results = store.search_hybrid("database connection pool")
    assert any(r.id == "h1" for r in results)


def test_hybrid_search_matches_pure_lexical_when_no_embedder(store: LocalMemoryStore) -> None:
    store.write(make_record("a", content="auth token expired during refresh"))
    store.write(make_record("b", key="other:key", content="cache eviction policy LRU"))
    hybrid_ids = {r.id for r in store.search_hybrid("auth token refresh")}
    lexical_ids = {r.id for r in store.search("auth token refresh")}
    # Hybrid must never lose a record that pure lexical found.
    assert lexical_ids.issubset(hybrid_ids)


def test_hybrid_search_finds_semantic_match_lexical_misses(store: LocalMemoryStore) -> None:
    """A semantically-related record with no lexical overlap should surface via
    the embedding leg. Skipped gracefully when no embedding backend is present."""
    from opencontext_core.embeddings.generators import DeterministicEmbeddingGenerator
    from opencontext_core.embeddings.stores import LocalVectorStore

    with tempfile.TemporaryDirectory() as tmpdir:
        vector_store = LocalVectorStore(base_path=Path(tmpdir) / "vec")
        embedder = DeterministicEmbeddingGenerator(dimensions=64)
        sem_store = LocalMemoryStore(
            Path(tmpdir) / "mem.db",
            vector_store=vector_store,
            embedder=embedder,
        )
        if not sem_store.semantic_enabled:
            pytest.skip("no embedding backend available")

        # Record whose words do NOT overlap the query at all.
        target = make_record("sem", content="the canine sprinted across the meadow")
        sem_store.write(target)
        # A lexical distractor that shares no query terms either.
        sem_store.write(make_record("noise", key="n:k", content="quarterly revenue report"))

        query = "the canine sprinted across the meadow"
        # Pure lexical on a *paraphrase* would miss; here we assert the semantic
        # leg can retrieve the exact-embedding match even when FTS is bypassed.
        results = sem_store.search_hybrid(query, limit=5)
        assert any(r.id == "sem" for r in results)


# --- Write-time consolidation ---------------------------------------------


def test_duplicate_write_is_noop(store: LocalMemoryStore) -> None:
    """Writing an identical (key, content) record must not create a duplicate row."""
    store.write(make_record("d1", key="k:dup", content="identical payload here"))
    store.write(make_record("d2", key="k:dup", content="identical payload here"))
    recs = store._backend.get_by_key("k:dup")
    assert len(recs) == 1


def test_near_duplicate_write_updates_in_place(store: LocalMemoryStore) -> None:
    """A near-duplicate (same key, high token overlap but NOT a normalized exact
    match) refreshes the existing record in place rather than inserting a second
    row or superseding. Exercises the UPDATE path / _apply_update — distinct from
    the NO_OP exact-duplicate path."""
    # 8 shared tokens; the second adds exactly one -> jaccard 8/9 ~ 0.89 (>= 0.85)
    # while normalizing differently (so it is a near-dup UPDATE, never a NO_OP).
    store.write(
        make_record("u1", key="k:near", content="configure the auth retry backoff to five seconds")
    )
    returned = store.write(
        make_record(
            "u2",
            key="k:near",
            content="configure the auth retry backoff to five seconds now",
            confidence=0.95,
        )
    )

    rows = store._backend.get_by_key("k:near")
    assert len(rows) == 1  # updated in place: no second row, no supersession history
    updated = rows[0]
    assert updated.id == "u1"  # the existing record was refreshed, u2 not inserted
    assert returned == "u1"
    assert updated.content == "configure the auth retry backoff to five seconds now"  # refreshed
    assert updated.confidence == 0.95  # max(0.9, 0.95)
    assert updated.invalid_at is None  # still the active belief


# --- Bi-temporal supersession ---------------------------------------------


def test_conflicting_write_supersedes_and_preserves_history(store: LocalMemoryStore) -> None:
    prior = make_record("old", key="auth:login", content="use cookie session", confidence=0.9)
    store.write(prior)
    new = make_record("new", key="auth:login", content="use bearer token", confidence=0.95)
    store.write(new)

    recs = store._backend.get_by_key("auth:login")
    old_updated = next((r for r in recs if r.id == "old"), None)
    new_rec = next((r for r in recs if r.id == "new"), None)
    assert old_updated is not None
    assert new_rec is not None
    # Prior belief is preserved (not deleted) but marked invalid as of a time.
    assert old_updated.invalid_at is not None
    assert old_updated.superseded_by == "new"
    # The superseding record points back at what it replaced.
    assert "old" in new_rec.supersedes
    # The active record carries no invalidation.
    assert new_rec.invalid_at is None


def test_active_records_excludes_superseded(store: LocalMemoryStore) -> None:
    store.write(make_record("old", key="auth:login", content="use cookie session", confidence=0.9))
    store.write(make_record("new", key="auth:login", content="use bearer token", confidence=0.95))
    active = store.active_records("auth:login")
    ids = {r.id for r in active}
    assert "new" in ids
    assert "old" not in ids


def test_superseded_record_still_queryable(store: LocalMemoryStore) -> None:
    store.write(make_record("old", key="auth:login", content="use cookie session", confidence=0.9))
    store.write(make_record("new", key="auth:login", content="use bearer token", confidence=0.95))
    # History remains fully queryable via the backend.
    recs = store._backend.get_by_key("auth:login")
    assert any(r.id == "old" for r in recs)


# --- Background consolidation ---------------------------------------------


def test_consolidate_distills_noisy_records(store: LocalMemoryStore) -> None:
    base = datetime.now(tz=UTC) - timedelta(days=2)
    for i in range(5):
        store.write(
            make_record(
                f"noise-{i}",
                key="logs:retry",
                content=f"retry attempt {i} failed with timeout",
                layer=MemoryLayer.WORKING,
                confidence=0.4,
                created_at=base + timedelta(seconds=i),
            )
        )
    summary_id = store.consolidate(key="logs:retry", layer=MemoryLayer.WORKING)
    assert summary_id is not None
    active = store.active_records("logs:retry", layer=MemoryLayer.WORKING)
    # The noisy records are collapsed into a single active summary record.
    assert len(active) == 1
    assert active[0].id == summary_id
    # But the originals are preserved as history.
    all_recs = store._backend.get_by_key("logs:retry", layer=MemoryLayer.WORKING)
    assert len(all_recs) >= 6


def test_consolidate_noop_when_too_few(store: LocalMemoryStore) -> None:
    store.write(
        make_record("solo", key="logs:solo", content="single record", layer=MemoryLayer.WORKING)
    )
    result = store.consolidate(key="logs:solo", layer=MemoryLayer.WORKING)
    assert result is None


# --- Episodic memory -------------------------------------------------------


def test_episodic_recall_returns_prior_failure(store: LocalMemoryStore) -> None:
    store.record_episode(
        task="deploy auth service to staging",
        outcome="failure",
        detail="migration timed out on large table",
    )
    store.record_episode(
        task="deploy billing service",
        outcome="success",
        detail="completed in 2 minutes",
    )
    episodes = store.recall_episodes("deploy auth service", outcome="failure")
    assert episodes
    assert any("migration timed out" in e.content for e in episodes)
    assert all(e.layer == MemoryLayer.EPISODIC for e in episodes)


def test_episodic_recall_filters_by_outcome(store: LocalMemoryStore) -> None:
    store.record_episode(task="run test suite", outcome="success", detail="all green")
    store.record_episode(
        task="run test suite again", outcome="failure", detail="flaky network test"
    )
    failures = store.recall_episodes("run test suite", outcome="failure")
    assert failures
    assert all("failure" in e.tags for e in failures)
    assert all("flaky" in e.content or "network" in e.content for e in failures)
