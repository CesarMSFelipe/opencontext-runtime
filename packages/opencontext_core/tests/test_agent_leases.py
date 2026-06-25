"""Tests for D5: AgentCoordinationStore lease acquire/release/signal round-trip."""

from __future__ import annotations

import tempfile
from datetime import UTC, timedelta
from pathlib import Path

import pytest

from opencontext_core.workflow.leases import AgentCoordinationStore, AgentLeaseStatus
from opencontext_core.workflow.signals import AgentSignalKind


class TestAgentLeaseFields:
    def test_lease_fields_accessible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AgentCoordinationStore(Path(tmp) / "coord.db")
            lease = store.acquire("agent-1", "run-1", "explore", timedelta(hours=1))
            assert lease.lease_id
            assert lease.agent_id == "agent-1"
            assert lease.acquired_at is not None
            assert lease.expires_at is not None
            assert lease.status == AgentLeaseStatus.ACTIVE


class TestAgentCoordinationStoreRoundTrip:
    def test_acquire_release_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AgentCoordinationStore(Path(tmp) / "coord.db")
            lease = store.acquire("agent-2", "run-2", "design", timedelta(minutes=30))
            assert lease.status == AgentLeaseStatus.ACTIVE

            store.release(lease.lease_id)
            retrieved = store.get_lease(lease.lease_id)
            assert retrieved is not None
            assert retrieved.status == AgentLeaseStatus.RELEASED

    def test_acquire_signal_release_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AgentCoordinationStore(Path(tmp) / "coord.db")
            lease = store.acquire("agent-3", "run-3", "apply", timedelta(hours=2))

            signal = store.signal(lease.lease_id, AgentSignalKind.STARTED)
            assert signal.lease_id == lease.lease_id
            assert signal.kind == AgentSignalKind.STARTED

            store.release(lease.lease_id)
            signals = store.get_signals(lease.lease_id)
            assert len(signals) == 1
            assert signals[0].kind == AgentSignalKind.STARTED

            final = store.get_lease(lease.lease_id)
            assert final.status == AgentLeaseStatus.RELEASED

    def test_lease_survives_store_restart(self) -> None:
        """Lease written to SQLite must be readable after re-opening the store."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "coord.db"
            store1 = AgentCoordinationStore(db_path)
            lease = store1.acquire("agent-4", "run-4", "verify", timedelta(hours=1))
            lease_id = lease.lease_id

            # Re-open store (simulates process restart).
            store2 = AgentCoordinationStore(db_path)
            retrieved = store2.get_lease(lease_id)
            assert retrieved is not None
            assert retrieved.status == AgentLeaseStatus.ACTIVE
            assert retrieved.agent_id == "agent-4"

    def test_duplicate_acquire_raises_when_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AgentCoordinationStore(Path(tmp) / "coord.db")
            store.acquire("agent-5", "run-5", "spec", timedelta(hours=1))
            with pytest.raises(RuntimeError, match="Active lease"):
                store.acquire("agent-5b", "run-5", "spec", timedelta(hours=1))

    def test_expired_lease_allows_new_acquire(self) -> None:
        """An expired lease (past expires_at) should allow a new acquire."""
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "coord.db"
            store = AgentCoordinationStore(db_path)
            lease = store.acquire("agent-6", "run-6", "tasks", timedelta(seconds=1))

            # Manually backdate expires_at to simulate expiry.
            from datetime import datetime

            past = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                "UPDATE agent_leases SET expires_at = ? WHERE lease_id = ?",
                (past, lease.lease_id),
            )
            conn.commit()
            conn.close()

            # Should succeed because old lease is now expired.
            new_lease = store.acquire("agent-6b", "run-6", "tasks", timedelta(hours=1))
            assert new_lease.lease_id != lease.lease_id
            assert new_lease.status == AgentLeaseStatus.ACTIVE


class TestCoordinatorPolicyUnchanged:
    def test_coordinator_policy_still_raises_on_non_main_thread(self) -> None:
        """D5 must not weaken CoordinatorPolicy.assert_allowed."""
        import threading

        from opencontext_core.workflow.coordinator_policy import CoordinatorPolicy

        policy = CoordinatorPolicy()
        # Main thread should be allowed.
        policy.assert_allowed(thread_id=threading.get_ident())

        # A synthetic non-main thread_id should raise.
        with pytest.raises((RuntimeError, ValueError, AssertionError)):
            policy.assert_allowed(thread_id=-1)
