"""Retention policy acceptance (REQ-data-gov-003, PR-R2-B).

Contract:
- ``RetentionPolicy`` carries per-classification window in days:
    * PUBLIC=∞ (None sentinel = never purge)
    * INTERNAL=30
    * CONFIDENTIAL=7
    * RESTRICTED=0  (never written to durable storage beyond the active run)
- ``enforce_retention(records, policy, now, audit=None)`` returns the
  :class:`PurgeReceipt` list: each receipt carries the record id, its
  classification, and the event kind. When *audit* is provided, an entry is
  written per receipt (defense in depth: the audit trail is the only place the
  original record id is preserved once the record itself is dropped).
- RESTRICTED records are always purged, regardless of age.
- A record whose ``age_days`` is below its window is **kept**.
"""
from __future__ import annotations

from opencontext_core.governance.classification import DataSensitivity
from opencontext_core.governance.retention import (
    PurgeReceipt,
    RetentionPolicy,
    enforce_retention,
)


def _record(record_id: str, sensitivity: DataSensitivity, age_days: int) -> dict:
    return {"id": record_id, "sensitivity": sensitivity, "age_days": age_days}


class TestRetentionPolicyDefaults:
    def test_default_policy_matches_spec(self) -> None:
        p = RetentionPolicy()
        assert p.window_for(DataSensitivity.PUBLIC) is None  # never
        assert p.window_for(DataSensitivity.INTERNAL) == 30
        assert p.window_for(DataSensitivity.CONFIDENTIAL) == 7
        assert p.window_for(DataSensitivity.RESTRICTED) == 0

    def test_restricted_window_is_zero_and_not_configurable(self) -> None:
        # Even with custom values for other levels, RESTRICTED is locked to 0.
        p = RetentionPolicy(public_days=10, internal_days=15, confidential_days=3)
        assert p.window_for(DataSensitivity.RESTRICTED) == 0


class TestEnforceRetention:
    def test_public_never_purged(self) -> None:
        policy = RetentionPolicy()
        records = [_record("p1", DataSensitivity.PUBLIC, age_days=10_000)]
        receipts = enforce_retention(records, policy, now=0)
        assert receipts == []

    def test_internal_within_window_kept(self) -> None:
        policy = RetentionPolicy()
        records = [_record("i1", DataSensitivity.INTERNAL, age_days=10)]
        receipts = enforce_retention(records, policy, now=0)
        assert receipts == []

    def test_internal_past_window_purged(self) -> None:
        policy = RetentionPolicy()
        records = [_record("i1", DataSensitivity.INTERNAL, age_days=31)]
        receipts = enforce_retention(records, policy, now=0)
        assert len(receipts) == 1
        assert receipts[0].record_id == "i1"
        assert receipts[0].sensitivity is DataSensitivity.INTERNAL
        assert receipts[0].event == "purge_past_window"

    def test_confidential_past_window_purged(self) -> None:
        policy = RetentionPolicy()
        records = [_record("c1", DataSensitivity.CONFIDENTIAL, age_days=8)]
        receipts = enforce_retention(records, policy, now=0)
        assert len(receipts) == 1
        assert receipts[0].sensitivity is DataSensitivity.CONFIDENTIAL

    def test_restricted_always_purged_even_when_fresh(self) -> None:
        policy = RetentionPolicy()
        records = [_record("r1", DataSensitivity.RESTRICTED, age_days=0)]
        receipts = enforce_retention(records, policy, now=0)
        assert len(receipts) == 1
        assert receipts[0].event == "purge_at_run_end"

    def test_mixed_records_returns_only_purge_receipts(self) -> None:
        policy = RetentionPolicy()
        records = [
            _record("a", DataSensitivity.PUBLIC, 9_999),
            _record("b", DataSensitivity.INTERNAL, 10),       # keep
            _record("c", DataSensitivity.INTERNAL, 31),       # purge
            _record("d", DataSensitivity.CONFIDENTIAL, 7),     # keep
            _record("e", DataSensitivity.CONFIDENTIAL, 8),     # purge
            _record("f", DataSensitivity.RESTRICTED, 0),       # purge
        ]
        receipts = enforce_retention(records, policy, now=0)
        purged_ids = {r.record_id for r in receipts}
        assert purged_ids == {"c", "e", "f"}
        assert all(isinstance(r, PurgeReceipt) for r in receipts)


class TestEnforceRetentionAuditHook:
    def test_audit_hook_receives_one_event_per_receipt(self) -> None:
        policy = RetentionPolicy()
        records = [
            _record("x", DataSensitivity.RESTRICTED, 0),
            _record("y", DataSensitivity.INTERNAL, 31),
        ]
        captured: list[tuple[str, DataSensitivity, str]] = []

        def audit(record_id: str, sensitivity: DataSensitivity, event: str) -> None:
            captured.append((record_id, sensitivity, event))

        enforce_retention(records, policy, now=0, audit=audit)
        assert ("x", DataSensitivity.RESTRICTED, "purge_at_run_end") in captured
        assert ("y", DataSensitivity.INTERNAL, "purge_past_window") in captured
