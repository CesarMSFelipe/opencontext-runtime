"""opencontext_memory.models — public Pydantic types + lifecycle-aware record.

Re-exports the canonical record + receipt shapes so the host can do
``from opencontext_memory import MemoryRecord, SaveReceipt, ...`` in a
single line (per the design.md §Public Python API).

* ``MemoryRecord`` — extends :class:`opencontext_core.models.agent_memory.MemoryRecord`
  with the lifecycle fields the SQLite store tracks (``review_after``,
  ``lifecycle_state``, ``pinned``). Methods:
  - ``state(now=None)`` — pure-function derivation of ``"active"`` /
    ``"needs_review"``.
* ``MemoryRecordLite`` — alias of the core schema for callers that do
  NOT need the lifecycle extension.
* ``SaveReceipt``, ``CandidateEnvelope``, ``ConflictEnvelope``,
  ``RelationRow``, ``SessionRecord``, ``DetectionResult`` — re-exports.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from opencontext_core.models.agent_memory import MemoryRecord as CoreMemoryRecord
from opencontext_memory.conflict import CandidateEnvelope, ConflictEnvelope
from opencontext_memory.lifecycle import state as _state
from opencontext_memory.project import DetectionResult
from opencontext_memory.store.relations import RelationRow
from opencontext_memory.tools.mem_save import SaveReceipt
from opencontext_memory.tools.mem_session_start import SessionRecord


class MemoryRecord(CoreMemoryRecord):
    """OpenContext-memory-flavored MemoryRecord with lifecycle attrs.

    Extends the canonical core schema with the three fields the SQLite
    store tracks (``review_after``, ``lifecycle_state``, ``pinned``).
    Adds the ``state`` method that mirrors
    :func:`opencontext_memory.lifecycle.state`.
    """

    model_config = ConfigDict(extra="forbid")

    review_after: datetime | None = Field(
        default=None,
        description="ISO timestamp; past values flip the record to needs_review.",
    )
    lifecycle_state: Literal["active", "needs_review"] = Field(
        default="active",
        description="Derived state; cached in-store for index-backed queries.",
    )
    pinned: bool = Field(default=False, description="Pin against lifecycle decay (REQ-OMT-014).")

    def state(self, *, now: datetime | None = None) -> Literal["active", "needs_review"]:
        """Pure-function derivation of this record's lifecycle state."""
        return _state(self.review_after, now=now)


# Canonical alias for callers that don't care about lifecycle attrs.
MemoryRecordLite = CoreMemoryRecord


# Public re-exports — keep imports flat for the host.
CandidateEnvelopeLiteral = CandidateEnvelope  # alias for symmetry
# Re-export the lifecycle pure-function under its canonical name.
state = _state


__all__ = [
    "CandidateEnvelope",
    "CandidateEnvelopeLiteral",
    "ConflictEnvelope",
    "DetectionResult",
    "MemoryRecord",
    "MemoryRecordLite",
    "RelationRow",
    "SaveReceipt",
    "SessionRecord",
    "state",
]
