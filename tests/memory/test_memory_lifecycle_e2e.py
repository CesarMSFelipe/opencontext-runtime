"""E2E tests for the memory save → reuse → mark_reviewed → purge lifecycle.

P1.4: End-to-end coverage for the real memory lifecycle through actual entry
points against a tmp store. Tests verify each stage in order:

1. Save  — mem_save persists the observation, returns a receipt.
2. Reuse — mem_search retrieves the saved observation by BM25.
3. Approve/harvest (mark_reviewed) — lifecycle.mark_reviewed() resets
   review_after, transitioning needs_review → active.
4. Purge — mem_delete removes the observation; subsequent retrieval raises.

NOTE: There is NO "require_approval before retrieval" gate in the memory
package. Records are immediately searchable after save. The approval concept
in this codebase refers to the harness write-approval gate (apply phase), not
a memory visibility gate. That missing feature is not fabricated here.

NOTE: "context compression / protected spans" does not exist as a memory
feature and is out of scope (needs design). This test does not fabricate it.

All tests use a tmp SQLite store; the real ~/.opencontext store is never
touched (no HOME or real path used).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from opencontext_memory import MemoryStore
from opencontext_memory.lifecycle import mark_reviewed
from opencontext_memory.lifecycle import state as lifecycle_state
from opencontext_memory.tools.mem_delete import mem_delete
from opencontext_memory.tools.mem_get_observation import MemoryNotFound, mem_get_observation
from opencontext_memory.tools.mem_save import mem_save
from opencontext_memory.tools.mem_search import mem_search

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> MemoryStore:
    """Open an isolated store under tmp_path — never the real ~/.opencontext."""
    return MemoryStore.open(tmp_path / "memory_e2e.sqlite3")


# ---------------------------------------------------------------------------
# Stage 1 — Save
# ---------------------------------------------------------------------------


class TestMemoryLifecycleSave:
    """mem_save correctly persists an observation with all required fields."""

    def test_save_returns_receipt_with_id(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        receipt = mem_save(
            store=store,
            session_id="e2e-sess-1",
            project="test-project",
            title="Auth bug: 500 on /login",
            content="Users receive HTTP 500 on POST /login due to missing null check.",
            type="bugfix",
            topic_key="bugs/auth-500",
        )
        assert receipt.receipt.id >= 1
        assert receipt.receipt.title == "Auth bug: 500 on /login"
        assert receipt.receipt.project == "test-project"

    def test_save_observation_is_immediately_retrievable(self, tmp_path: Path) -> None:
        """No approval gate blocks retrieval — records are searchable right after save."""
        store = _make_store(tmp_path)
        receipt = mem_save(
            store=store,
            session_id="e2e-sess-1",
            project="test-project",
            title="JWT expiry decision",
            content="JWT tokens expire after 24 h; refresh tokens rotate on every use.",
            type="decision",
        )
        # Immediately searchable — no approval step required.
        hits = mem_search(store=store, query="JWT expiry", project="test-project")
        assert len(hits) >= 1
        assert any(h["id"] == receipt.receipt.id for h in hits)

    def test_save_empty_content_raises(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        with pytest.raises(ValueError, match="content_required"):
            mem_save(
                store=store,
                session_id="e2e-sess-2",
                project="test-project",
                title="Empty",
                content="",
            )


# ---------------------------------------------------------------------------
# Stage 2 — Reuse (search)
# ---------------------------------------------------------------------------


class TestMemoryLifecycleReuse:
    """mem_search returns previously saved observations by BM25 relevance."""

    def test_search_finds_saved_observation(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_save(
            store=store,
            session_id="e2e-sess-1",
            project="proj",
            title="Database connection pool tuning",
            content="Increased max_overflow to 20 to handle burst traffic.",
            type="decision",
        )
        hits = mem_search(store=store, query="connection pool", project="proj")
        assert len(hits) >= 1
        assert hits[0]["title"] == "Database connection pool tuning"

    def test_search_respects_project_filter(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        mem_save(
            store=store,
            session_id="e2e-sess-1",
            project="proj-A",
            title="Alpha caching strategy",
            content="Use Redis for session caching in project Alpha.",
            type="decision",
        )
        mem_save(
            store=store,
            session_id="e2e-sess-1",
            project="proj-B",
            title="Beta caching strategy",
            content="Use Memcached for session caching in project Beta.",
            type="decision",
        )
        hits_a = mem_search(store=store, query="caching", project="proj-A")
        assert all(h["project"] == "proj-A" for h in hits_a)
        hits_b = mem_search(store=store, query="caching", project="proj-B")
        assert all(h["project"] == "proj-B" for h in hits_b)

    def test_search_returns_empty_for_unknown_query(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        hits = mem_search(store=store, query="xyznonexistentzyz")
        assert hits == []


# ---------------------------------------------------------------------------
# Stage 3 — Approve / harvest (mark_reviewed)
# ---------------------------------------------------------------------------


class TestMemoryLifecycleMarkReviewed:
    """lifecycle.mark_reviewed() resets review_after and restores active state."""

    def _save_with_past_review_after(
        self, store: MemoryStore, *, project: str, session_id: str
    ) -> int:
        """Save a row and directly stamp review_after in the past to simulate decay."""
        receipt = mem_save(
            store=store,
            session_id=session_id,
            project=project,
            title="Stale architecture decision",
            content="We chose a monolith in 2020; may need revisiting.",
            type="architecture",
        )
        obs_id = receipt.receipt.id
        past = (datetime.now(UTC) - timedelta(days=200)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with store._connect() as conn:
            conn.execute(
                "UPDATE observations SET review_after = ? WHERE id = ?",
                (past, obs_id),
            )
        return obs_id

    def test_mark_reviewed_resets_review_after_to_future(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        obs_id = self._save_with_past_review_after(
            store, project="proj", session_id="e2e-sess-1"
        )
        # Before mark_reviewed, the row is needs_review.
        with store._connect() as conn:
            row = conn.execute(
                "SELECT review_after FROM observations WHERE id = ?", (obs_id,)
            ).fetchone()
        assert lifecycle_state(row["review_after"]) == "needs_review"

        # mark_reviewed resets the clock.
        result = mark_reviewed(store, observation_id=obs_id)
        assert result["audit"]["prior_state"] == "needs_review"
        assert result["audit"]["new_state"] == "active"

        # The row is now active again.
        with store._connect() as conn:
            row = conn.execute(
                "SELECT review_after, lifecycle_state FROM observations WHERE id = ?",
                (obs_id,),
            ).fetchone()
        assert lifecycle_state(row["review_after"]) == "active"
        assert row["lifecycle_state"] == "active"

    def test_mark_reviewed_on_already_active_keeps_active(self, tmp_path: Path) -> None:
        """mark_reviewed on an active row still succeeds — idempotent re-stamp."""
        store = _make_store(tmp_path)
        receipt = mem_save(
            store=store,
            session_id="e2e-sess-1",
            project="proj",
            title="Active observation",
            content="This was just reviewed.",
            type="decision",
        )
        obs_id = receipt.receipt.id
        result = mark_reviewed(store, observation_id=obs_id)
        assert result["audit"]["new_state"] == "active"

    def test_mark_reviewed_on_deleted_row_raises(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        receipt = mem_save(
            store=store,
            session_id="e2e-sess-1",
            project="proj",
            title="To be deleted",
            content="Will be deleted before mark_reviewed is called.",
            type="decision",
        )
        obs_id = receipt.receipt.id
        mem_delete(store, observation_id=obs_id)  # soft-delete
        with pytest.raises(LookupError, match=f"memory_not_found:{obs_id}"):
            mark_reviewed(store, observation_id=obs_id)


# ---------------------------------------------------------------------------
# Stage 4 — Purge (delete)
# ---------------------------------------------------------------------------


class TestMemoryLifecyclePurge:
    """mem_delete removes the observation; subsequent access raises MemoryNotFound."""

    def test_soft_delete_hides_from_get_observation(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        receipt = mem_save(
            store=store,
            session_id="e2e-sess-1",
            project="proj",
            title="Obsolete config decision",
            content="We used config.ini in legacy; now obsolete.",
            type="decision",
        )
        obs_id = receipt.receipt.id
        # Soft-delete.
        mem_delete(store, observation_id=obs_id)
        # Subsequent retrieval raises.
        with pytest.raises(MemoryNotFound):
            mem_get_observation(store, observation_id=obs_id)

    def test_soft_delete_removes_from_search(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        receipt = mem_save(
            store=store,
            session_id="e2e-sess-1",
            project="proj",
            title="Temporary spike decision",
            content="Used a temporary spike approach for the prototype.",
            type="decision",
        )
        obs_id = receipt.receipt.id
        # Visible before delete.
        before = mem_search(store=store, query="temporary spike", project="proj")
        assert any(h["id"] == obs_id for h in before)
        # Not visible after soft delete.
        mem_delete(store, observation_id=obs_id)
        after = mem_search(store=store, query="temporary spike", project="proj")
        assert not any(h["id"] == obs_id for h in after)

    def test_hard_delete_is_permanent(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        receipt = mem_save(
            store=store,
            session_id="e2e-sess-1",
            project="proj",
            title="Hard delete target",
            content="This row will be hard-deleted.",
            type="decision",
        )
        obs_id = receipt.receipt.id
        mem_delete(store, observation_id=obs_id, hard=True)
        with pytest.raises(MemoryNotFound):
            mem_get_observation(store, observation_id=obs_id)


# ---------------------------------------------------------------------------
# Full pipeline E2E: save → search → mark_reviewed → delete → confirm gone
# ---------------------------------------------------------------------------


class TestMemoryLifecycleFullPipeline:
    """Single E2E flow exercising all four real lifecycle stages in sequence."""

    def test_full_lifecycle_save_search_review_delete(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)

        # Stage 1 — Save.
        receipt = mem_save(
            store=store,
            session_id="e2e-pipeline-sess",
            project="pipeline-project",
            title="Token rotation strategy",
            content=(
                "Refresh tokens rotate on each use. Access tokens expire in 15 min. "
                "Revoked tokens are stored in a deny-list for the remaining TTL."
            ),
            type="decision",
            topic_key="auth/token-rotation",
        )
        obs_id = receipt.receipt.id
        assert obs_id >= 1

        # Stage 2 — Reuse: record is searchable immediately (no approval gate).
        hits = mem_search(
            store=store, query="token rotation", project="pipeline-project"
        )
        assert any(h["id"] == obs_id for h in hits), "Record must be searchable after save"

        # Simulate lifecycle decay: stamp review_after in the past.
        past = (datetime.now(UTC) - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with store._connect() as conn:
            conn.execute(
                "UPDATE observations SET review_after = ? WHERE id = ?",
                (past, obs_id),
            )
        with store._connect() as conn:
            row = conn.execute(
                "SELECT review_after FROM observations WHERE id = ?", (obs_id,)
            ).fetchone()
        assert lifecycle_state(row["review_after"]) == "needs_review"

        # Stage 3 — Approve/harvest: mark_reviewed transitions back to active.
        review_result = mark_reviewed(store, observation_id=obs_id)
        assert review_result["audit"]["prior_state"] == "needs_review"
        assert review_result["audit"]["new_state"] == "active"

        # Stage 4 — Purge: soft-delete the record.
        mem_delete(store, observation_id=obs_id)
        # Confirm it is gone from search and retrieval.
        hits_after = mem_search(
            store=store, query="token rotation", project="pipeline-project"
        )
        assert not any(h["id"] == obs_id for h in hits_after), (
            "Soft-deleted record must not appear in search results"
        )
        with pytest.raises(MemoryNotFound):
            mem_get_observation(store, observation_id=obs_id)

    def test_no_approval_gate_blocks_search(self, tmp_path: Path) -> None:
        """Confirm: there is NO require_approval gate blocking mem_search.

        Records saved to the memory store are immediately searchable without any
        approval or harvest step. The 'approval' concept in this codebase refers
        to the harness apply-write gate, not a memory visibility control.
        """
        store = _make_store(tmp_path)
        receipt = mem_save(
            store=store,
            session_id="e2e-no-approval-sess",
            project="test",
            title="Immediate visibility check",
            content="This record should be immediately findable without approval.",
            type="decision",
        )
        # No approval step at all — search directly after save.
        hits = mem_search(store=store, query="immediate visibility", project="test")
        assert any(h["id"] == receipt.receipt.id for h in hits), (
            "mem_search must return the record without any approval gate"
        )
