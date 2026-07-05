"""Tests for the memory lifecycle module (T2.29).

Per strict-TDD: this file is the source of truth for the
``opencontext_memory.lifecycle`` contract. The production module lands in
T2.30 to turn these RED tests GREEN; the
:func:`opencontext_memory.tools.mem_review.mem_review` wrapper is refactored
in the same batch to delegate ``mark_reviewed`` to the lifecycle module and
import ``DECAY_DAYS`` from there, so the existing PR2.c.ii tests
(``test_REQ_OMT_009_*``) keep passing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from opencontext_memory import MemoryStore, Observation
from opencontext_memory.lifecycle import (
    DECAY_DAYS,
    LIFECYCLE_OVERRIDES_ENV,
    _decay_for_type,
    mark_reviewed,
    state,
)

# ---------------------------------------------------------------------------
# REQ-OML-001 — state() derivation
# ---------------------------------------------------------------------------


def test_REQ_OML_001_state_active_when_review_after_is_none() -> None:
    """review_after=None → always active."""
    assert state(None) == "active"


def test_REQ_OML_001_state_active_before_review_after() -> None:
    """review_after in the future → active."""
    now = datetime(2026, 7, 1, tzinfo=UTC)
    future = now + timedelta(days=1)
    assert state(future, now=now) == "active"


def test_REQ_OML_001_state_needs_review_after_review_after() -> None:
    """review_after in the past → needs_review."""
    now = datetime(2026, 7, 1, tzinfo=UTC)
    past = now - timedelta(hours=1)
    assert state(past, now=now) == "needs_review"


def test_REQ_OML_001_state_needs_review_at_exact_boundary() -> None:
    """review_after == now is inclusive on the needs_review side."""
    now = datetime(2026, 7, 1, tzinfo=UTC)
    assert state(now, now=now) == "needs_review"


# ---------------------------------------------------------------------------
# REQ-OML-002 — per-type decay policy + env overrides
# ---------------------------------------------------------------------------


def test_REQ_OML_002_decision_record_decays_90_days() -> None:
    """Decision → 90 days per the canonical table."""
    assert _decay_for_type("decision") == 90
    assert DECAY_DAYS["decision"] == 90


def test_REQ_OML_002_architecture_record_decays_180_days() -> None:
    """Architecture → 180 days per the canonical table."""
    assert _decay_for_type("architecture") == 180
    assert DECAY_DAYS["architecture"] == 180


def test_REQ_OML_002_unknown_type_falls_back_to_manual_default() -> None:
    """Unknown types fall back to the manual default (180 days)."""
    assert _decay_for_type("not_in_table") == _decay_for_type("manual")


def test_REQ_OML_002_env_override_flips_one_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting the env override JSON flips one specific type."""
    monkeypatch.setenv(LIFECYCLE_OVERRIDES_ENV, '{"decision": 30}')
    assert _decay_for_type("decision") == 30


def test_REQ_OML_002_env_override_only_affects_named_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Other types keep their canonical decay even when override is set."""
    monkeypatch.setenv(LIFECYCLE_OVERRIDES_ENV, '{"decision": 30}')
    assert _decay_for_type("architecture") == 180


def test_REQ_OML_002_malformed_env_override_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed JSON env value raises ``ValueError`` instead of falling back silently."""
    monkeypatch.setenv(LIFECYCLE_OVERRIDES_ENV, "{not json}")
    with pytest.raises(ValueError, match=r"invalid_decay_overrides"):
        _decay_for_type("decision")


# ---------------------------------------------------------------------------
# REQ-OML-003 + REQ-OML-004 — mark_reviewed resets decay clock + audit
# ---------------------------------------------------------------------------


def test_REQ_OML_003_mark_reviewed_resets_review_after_for_decision(
    store_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``mark_reviewed`` on a decision row computes roughly ``NOW + 90 days``."""
    store = MemoryStore.open(store_db)
    obs_id = store.write(
        Observation(
            session_id="s-1",
            title="d",
            content="c",
            project="P",
            type="decision",
            review_after="2000-01-01T00:00:00Z",
        )
    )

    before = datetime.now(tz=UTC)
    payload = mark_reviewed(store, observation_id=obs_id)
    after = datetime.now(tz=UTC)

    new_after = datetime.strptime(payload["review_after"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    expected_min = before + timedelta(days=90) - timedelta(seconds=2)
    expected_max = after + timedelta(days=90) + timedelta(seconds=2)
    assert expected_min <= new_after <= expected_max


def test_REQ_OML_003_state_flips_to_active_after_mark_reviewed(
    store_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After ``mark_reviewed`` the freshly written ``review_after`` evaluates to ``active``."""
    store = MemoryStore.open(store_db)
    obs_id = store.write(
        Observation(
            session_id="s-1",
            title="d",
            content="c",
            project="P",
            type="decision",
        )
    )

    payload = mark_reviewed(store, observation_id=obs_id)
    new_after_dt = datetime.strptime(payload["review_after"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC
    )

    assert state(new_after_dt) == "active"


def test_REQ_OML_004_mark_reviewed_returns_audit_row(
    store_db: Path,
) -> None:
    """Audit row carried on the response: observation_id, reviewed_at, prior_state, new_state."""
    store = MemoryStore.open(store_db)
    obs_id = store.write(
        Observation(
            session_id="s-1",
            title="d",
            content="c",
            project="P",
            type="decision",
            review_after="2000-01-01T00:00:00Z",
        )
    )

    payload = mark_reviewed(store, observation_id=obs_id)

    audit = payload.get("audit", {})
    assert audit["observation_id"] == obs_id
    assert audit["prior_state"] == "needs_review"
    assert audit["new_state"] == "active"
    assert "reviewed_at" in audit


# ---------------------------------------------------------------------------
# REQ-OML-005 — soft-deleted records are excluded
# ---------------------------------------------------------------------------


def test_REQ_OML_005_mark_reviewed_on_soft_deleted_record_raises(
    store_db: Path,
) -> None:
    """A soft-deleted row triggers ``LookupError`` — we never resurrect them."""
    from opencontext_memory.tools.mem_delete import mem_delete

    store = MemoryStore.open(store_db)
    obs_id = store.write(
        Observation(session_id="s-1", title="d", content="c", project="P", type="decision")
    )
    mem_delete(store, observation_id=obs_id)

    with pytest.raises(LookupError, match=r"memory_not_found"):
        mark_reviewed(store, observation_id=obs_id)
