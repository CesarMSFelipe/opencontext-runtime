"""OpenContext memory v2 (PR-014 / SPEC §3.2 memory).

Public surface for the memory layer: models, conflict resolution, the
harness, and the promotion gate. The memory v2 module never mutates
the KG directly — promotion is gated by the harness and the v2
promotion gate.
"""

from __future__ import annotations

__capability__ = "memory.v2"
