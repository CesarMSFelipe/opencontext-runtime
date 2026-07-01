from __future__ import annotations

"""Retention policy (REQ-data-gov-003, PR-R2-B).

Purges records on a per-classification schedule:

    PUBLIC=∞ (None sentinel), INTERNAL=30d, CONFIDENTIAL=7d, RESTRICTED=0d.

RESTRICTED is **non-configurable** — it must always be zero so the content never
reaches durable storage beyond the active run.

``enforce_retention`` returns one :class:`PurgeReceipt` per dropped record and
(optionally) calls an audit hook so the audit log is the only place the record
id is preserved once the record itself is gone.
"""


from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from opencontext_core.governance.classification import DataSensitivity

__all__ = [
    "AuditHook",
    "PurgeReceipt",
    "RetentionPolicy",
    "enforce_retention",
]


@dataclass(frozen=True)
class RetentionPolicy:
    """Per-classification retention window in days.

    ``public_days=None`` means "never purge". ``restricted_days`` is locked to
    0 regardless of constructor input — RESTRICTED content must never reach
    durable storage (OC-DATAGOV-001 §RETENTION).
    """

    public_days: int | None = None
    internal_days: int = 30
    confidential_days: int = 7
    restricted_days: int = 0

    def __post_init__(self) -> None:
        # Lock RESTRICTED to 0 — the dataclass is frozen, so we route through
        # object.__setattr__ to bypass the immutability guard for this one field.
        if self.restricted_days != 0:
            object.__setattr__(self, "restricted_days", 0)

    def window_for(self, sensitivity: DataSensitivity) -> int | None:
        if sensitivity is DataSensitivity.PUBLIC:
            return self.public_days
        if sensitivity is DataSensitivity.INTERNAL:
            return self.internal_days
        if sensitivity is DataSensitivity.CONFIDENTIAL:
            return self.confidential_days
        if sensitivity is DataSensitivity.RESTRICTED:
            return self.restricted_days
        raise ValueError(f"unknown sensitivity: {sensitivity!r}")


@dataclass(frozen=True)
class PurgeReceipt:
    """Audit-friendly receipt for a purged record."""

    record_id: str
    sensitivity: DataSensitivity
    event: str  # "purge_past_window" | "purge_at_run_end"


AuditHook = Callable[[str, DataSensitivity, str], None]


def enforce_retention(
    records: Iterable[dict[Any, Any]],
    policy: RetentionPolicy,
    now: float | int = 0,
    audit: AuditHook | None = None,
) -> list[PurgeReceipt]:
    """Return purge receipts for every record past its window.

    Each record dict must carry ``id``, ``sensitivity``, and ``age_days``. The
    *audit* callback (if provided) is invoked once per receipt with
    ``(record_id, sensitivity, event)``.
    """
    receipts: list[PurgeReceipt] = []
    for record in records:
        record_id = str(record["id"])
        sensitivity = record["sensitivity"]
        if not isinstance(sensitivity, DataSensitivity):
            sensitivity = DataSensitivity(sensitivity)
        age_days = int(record.get("age_days", 0))
        window = policy.window_for(sensitivity)
        if sensitivity is DataSensitivity.RESTRICTED:
            # Always purge, even at age 0.
            receipts.append(
                PurgeReceipt(record_id=record_id, sensitivity=sensitivity, event="purge_at_run_end")
            )
            continue
        if window is None:
            # PUBLIC: never purged.
            continue
        if age_days > window:
            receipts.append(
                PurgeReceipt(
                    record_id=record_id,
                    sensitivity=sensitivity,
                    event="purge_past_window",
                )
            )
    if audit is not None:
        for r in receipts:
            audit(r.record_id, r.sensitivity, r.event)
    return receipts
