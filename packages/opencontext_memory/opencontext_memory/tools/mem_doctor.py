"""mem_doctor — aggregate findings from the memory store.

REQ-OMT-018 — ``mem_doctor() -> DoctorReport``. PR2.c.ii ships the
``size``, ``conflicts``, and ``retention`` checks; the ``lifecycle``
check lands in PR2.d when ``lifecycle.py`` exists. The orchestrator
explicitly defers ``lifecycle`` to keep this sub-PR ≤ 400 LoC.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DoctorReport(BaseModel):
    """Aggregate report returned by :func:`mem_doctor`.

    ``state`` is the worst-case roll-up: ``"error"`` if any check failed,
    ``"ok"`` if all checks passed, ``"warn"`` if any check produced a
    non-blocking warning.
    """

    model_config = ConfigDict(extra="forbid")

    observations: int
    pending_judgments: int
    stale_observations: int
    checks: dict[str, str] = Field(default_factory=dict)
    state: str = "ok"


def mem_doctor(store: Any) -> DoctorReport:
    """Run the three checks and aggregate their findings.

    ``size`` — total observation count.
    ``conflicts`` — pending relation rows (judgment_status='pending').
    ``retention`` — observations whose ``review_after`` is in the past
    AND not null (i.e. would surface via :func:`mem_review`).
    """
    checks: dict[str, str] = {}
    state = "ok"
    with store._connect() as conn:
        observations = int(conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"])
        pending_judgments = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM memory_relations WHERE judgment_status = 'pending'"
            ).fetchone()["n"]
        )
        # Retention: rows whose review_after is in the past AND not null.
        # We use the same UTC ISO comparison mem_review uses.
        from datetime import UTC, datetime

        now_iso = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        stale = int(
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

    checks["size"] = "ok"
    checks["conflicts"] = "warn" if pending_judgments else "ok"
    checks["retention"] = "warn" if stale else "ok"

    if "warn" in checks.values():
        state = "warn"

    return DoctorReport(
        observations=observations,
        pending_judgments=pending_judgments,
        stale_observations=stale,
        checks=checks,
        state=state,
    )


__all__ = ["DoctorReport", "mem_doctor"]
