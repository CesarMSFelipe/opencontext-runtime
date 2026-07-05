"""opencontext_memory.diagnostic — 4-check aggregator for ``mem_doctor`` (REQ-OMT-018 + 021).

PR2.c.ii shipped ``tools/mem_doctor.py`` with the 3-check surface
(``size`` / ``conflicts`` / ``retention``); PR2.d adds the 4th check
(``lifecycle``) by extracting the aggregator into this module. The
existing tool wrapper now delegates to :func:`collect_findings` so the
public API stays backward-compatible while the implementation gains the
new check.

Each check returns ``(metric_value, status)`` so :func:`collect_findings`
can fold them into the 8-field :class:`DoctorReport`. The check statuses
are ``"ok"`` / ``"warn"`` / ``"error"``; the overall ``state`` rolls up
to ``"error"`` if any check is error, else ``"warn"`` if any check is
warn, else ``"ok"``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_memory.lifecycle import state


class DoctorReport(BaseModel):
    """Aggregate report returned by :func:`collect_findings` and :func:`mem_doctor`.

    ``state`` is the worst-case roll-up: ``"error"`` if any check failed,
    ``"warn"`` if any check produced a non-blocking warning, ``"ok"`` if
    all checks passed.

    The ``checks`` dict is keyed by check name and holds the rolled-up
    status string per check.
    """

    model_config = ConfigDict(extra="forbid")

    observations: int
    pending_judgments: int
    stale_observations: int
    needs_review: int = 0
    checks: dict[str, str] = Field(default_factory=dict)
    state: str = "ok"


def _size_check(store: Any) -> tuple[int, str]:
    with store._connect() as conn:
        n = int(conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"])
    return n, "ok"


def _conflicts_check(store: Any) -> tuple[int, str]:
    with store._connect() as conn:
        n = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM memory_relations WHERE judgment_status = 'pending'"
            ).fetchone()["n"]
        )
    return n, "warn" if n else "ok"


def _retention_check(store: Any) -> tuple[int, str]:
    now_iso = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with store._connect() as conn:
        n = int(
            conn.execute(
                """
                SELECT COUNT(*) AS n FROM observations
                WHERE deleted_at IS NULL
                  AND review_after IS NOT NULL
                  AND review_after < ?
                """,
                (now_iso,),
            ).fetchone()["n"]
        )
    return n, "warn" if n else "ok"


def _lifecycle_check(store: Any) -> tuple[int, str]:
    """Count rows whose current ``state()`` is ``"needs_review"``.

    Mirrors the same UTC-anchored boundary :func:`state` uses so the
    count stays consistent regardless of which timer the host picks.
    Excludes soft-deleted rows.
    """
    now = datetime.now(tz=UTC)
    n = 0
    with store._connect() as conn:
        rows = conn.execute(
            "SELECT review_after FROM observations WHERE deleted_at IS NULL"
        ).fetchall()
    for r in rows:
        if state(r["review_after"], now=now) == "needs_review":
            n += 1
    return n, "warn" if n else "ok"


def collect_findings(store: Any) -> DoctorReport:
    """Run all 4 checks and aggregate their findings.

    Returns a :class:`DoctorReport` with the 8 stable fields.
    """
    observations, size_status = _size_check(store)
    pending, conflicts_status = _conflicts_check(store)
    stale, retention_status = _retention_check(store)
    needs_review, lifecycle_status = _lifecycle_check(store)
    checks = {
        "size": size_status,
        "conflicts": conflicts_status,
        "retention": retention_status,
        "lifecycle": lifecycle_status,
    }
    if "error" in checks.values():
        overall = "error"
    elif "warn" in checks.values():
        overall = "warn"
    else:
        overall = "ok"
    return DoctorReport(
        observations=observations,
        pending_judgments=pending,
        stale_observations=stale,
        needs_review=needs_review,
        checks=checks,
        state=overall,
    )


__all__ = ["DoctorReport", "collect_findings"]
