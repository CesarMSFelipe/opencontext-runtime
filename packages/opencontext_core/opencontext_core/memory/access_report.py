"""MemoryAccessReport — per-phase read/write ledger (slice 5, CAP5.Memory).

Groups ``AccessEntry`` rows by ``phase_name`` so a run can later report which
memory keys each phase touched. Pure data: no IO, no conductor coupling, no
enumeration of runs.

Spec (CAP5.Memory):
- Scenario: Read access recorded — a phase reading ``spec/my-change`` must
  produce an entry ``{key, op: read, phase_name}``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Op = Literal["read", "write"]


@dataclass(frozen=True)
class AccessEntry:
    """One memory access: ``key``, ``op`` (read|write), ``phase_name``.

    Frozen so a logged access cannot be silently rewritten after recording —
    keeps the report an honest audit trail.
    """

    key: str
    op: Op
    phase_name: str


@dataclass
class MemoryAccessReport:
    """Phase-keyed ledger of memory accesses for a run.

    ``entries`` maps phase name -> ordered list of accesses recorded during
    that phase. Order within a phase preserves the sequence of calls so a
    downstream consumer can reconstruct the call trace.
    """

    entries: dict[str, list[AccessEntry]] = field(default_factory=dict)

    def record_read(self, key: str, phase: str) -> None:
        """Append a read access for ``key`` under ``phase``."""
        self.entries.setdefault(phase, []).append(AccessEntry(key=key, op="read", phase_name=phase))

    def record_write(self, key: str, phase: str) -> None:
        """Append a write access for ``key`` under ``phase``."""
        self.entries.setdefault(phase, []).append(
            AccessEntry(key=key, op="write", phase_name=phase)
        )


__all__ = ["AccessEntry", "MemoryAccessReport"]


if __name__ == "__main__":  # NOTE: tiny executable sanity check
    report = MemoryAccessReport()
    report.record_read("spec/foo", phase="spec")
    report.record_write("decisions/r", phase="apply")
    report.record_read("memory/working", phase="apply")
    assert set(report.entries) == {"spec", "apply"}
    assert report.entries["spec"][0].op == "read"
    assert report.entries["apply"][-1].op == "read"
    print("memory/access_report.py self-check passed.")
