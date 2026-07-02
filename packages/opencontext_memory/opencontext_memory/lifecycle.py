"""opencontext_memory.lifecycle — per-type decay + state derivation (REQ-OML-001..005).

The lifecycle module is the canonical home for the ``state()`` pure-function
AND the per-type decay table (decisions decay 90 days, architecture 180 days,
bugfix 30 days, etc.). PR2.c.ii shipped a minimal ``DECAY_DAYS`` dict
inline in :mod:`opencontext_memory.tools.mem_review`; that module now
imports :data:`DECAY_DAYS` and :func:`mark_reviewed` from here so there is
exactly one source of truth.

Decay overrides are applied via the environment variable
``OPENCONTEXT_MEMORY_DECAY_OVERRIDES`` — a JSON dict mapping ``type`` to
days. Malformed payloads raise :class:`ValueError` so the host fails fast
rather than silently reverting to defaults (the spec is explicit on this).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

# Public env-var name so tests + callers can reference the same string.
LIFECYCLE_OVERRIDES_ENV = "OPENCONTEXT_MEMORY_DECAY_OVERRIDES"

# NOTE: canonical per-type decay table. PR2.d replaces the inline
# 4-type subset mem_review shipped in PR2.c.ii with this 7-type version
# (pattern + config + discovery + manual default added).
DECAY_DAYS: dict[str, int] = {
    "decision": 90,
    "architecture": 180,
    "pattern": 180,
    "config": 365,
    "discovery": 60,
    "bugfix": 30,
    "manual": 180,  # catch-all default per spec
}


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _utcnow_iso() -> str:
    return _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_overrides() -> dict[str, int]:
    raw = os.environ.get(LIFECYCLE_OVERRIDES_ENV, "")
    raw = raw.strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_decay_overrides:{exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("invalid_decay_overrides:not_a_dict")
    out: dict[str, int] = {}
    for k, v in parsed.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid_decay_overrides:not_int:{k}") from exc
    return out


def _decay_for_type(obs_type: str | None) -> int:
    """Return the number of days added to now when an observation is reviewed.

    Resolution order:
        1. env override (``OPENCONTEXT_MEMORY_DECAY_OVERRIDES``) wins
        2. ``DECAY_DAYS[obs_type]`` if listed
        3. ``DECAY_DAYS['manual']`` (catch-all default)
    """
    if obs_type is None:
        return DECAY_DAYS["manual"]
    overrides = _env_overrides()
    if obs_type in overrides:
        return overrides[obs_type]
    return DECAY_DAYS.get(obs_type, DECAY_DAYS["manual"])


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def state(review_after: Any, *, now: datetime | None = None) -> Literal["active", "needs_review"]:
    """Pure-function derivation of ``MemoryRecord`` lifecycle state.

    Accepts ``None``, an ISO string (with or without trailing ``Z``), or a
    :class:`datetime` for ``review_after``. The boundary is inclusive — a
    row whose ``review_after == now`` is already ``"needs_review"`` (the
    clock has reached the deadline). A row with ``review_after`` in the
    future (or ``None``) is ``"active"``.

    Pure function; no DB I/O so tests call it with plain strings.
    """
    if review_after is None:
        return "active"
    if isinstance(review_after, datetime):
        ra_dt: datetime | None = review_after
    elif isinstance(review_after, str):
        ra_dt = _parse_iso(review_after)
    else:
        return "active"
    if ra_dt is None:
        return "active"
    if now is None:
        now = _utcnow()
    return "needs_review" if now >= ra_dt else "active"


def mark_reviewed(store: Any, *, observation_id: int) -> dict[str, Any]:
    """Reset ``review_after`` to ``now + decay_for_type(observation.type)``.

    Returns the refreshed observation row PLUS an ``audit`` sub-document
    carrying ``observation_id``, ``reviewed_at``, ``prior_state`` and
    ``new_state`` (REQ-OML-004). Soft-deleted rows raise
    ``LookupError("memory_not_found:<id>")`` so callers cannot resurrect
    ghost rows by triggering a refresh.
    """
    # Lazy import to avoid a cycles + keep the lifecycle module importable
    # from mem_get_observation tests without booting the full tool layer.
    from opencontext_memory.tools.mem_get_observation import mem_get_observation

    with store._connect() as conn:
        row = conn.execute(
            "SELECT type, review_after, deleted_at FROM observations WHERE id = ?",
            (observation_id,),
        ).fetchone()
        if row is None or row["deleted_at"] is not None:
            raise LookupError(f"memory_not_found:{observation_id}")
        obs_type = str(row["type"])
        prior_state_value = state(row["review_after"])
        decay_days = _decay_for_type(obs_type)
        new_after = (_utcnow() + timedelta(days=decay_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        reviewed_at = _utcnow_iso()
        conn.execute(
            """
            UPDATE observations
            SET review_after = ?, updated_at = ?, lifecycle_state = 'active'
            WHERE id = ?
            """,
            (new_after, reviewed_at, observation_id),
        )
    payload = mem_get_observation(store, observation_id=observation_id)
    payload["audit"] = {
        "observation_id": observation_id,
        "reviewed_at": reviewed_at,
        "prior_state": prior_state_value,
        "new_state": "active",
    }
    return payload


__all__ = [
    "DECAY_DAYS",
    "LIFECYCLE_OVERRIDES_ENV",
    "_decay_for_type",
    "_env_overrides",
    "mark_reviewed",
    "state",
]
