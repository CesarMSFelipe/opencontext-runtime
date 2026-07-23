"""PhaseMemoryGateway — the one shared service that wires memory into every SDD phase.

The SDD harness declares a per-phase read/write layer policy in
:mod:`opencontext_core.memory.phase_policy` (``PHASE_MEMORY_POLICY``). Until now
that policy was metadata only: no code recalled memory before a phase ran or
persisted memory after. This gateway ENFORCES it.

Design (single service, no per-phase edits):

* The harness runner builds ONE ``PhaseMemoryGateway`` from its already-resolved
  agent memory store and calls :meth:`recall` before each phase and
  :meth:`persist` after — the 8 individual phase ``run()`` bodies are untouched.
* :meth:`recall` searches EXACTLY the phase's declared ``read_layers`` and
  partitions the hits into ``trusted`` (belief still ``active``) vs
  ``needs_review`` (``candidate``/``stale``) so a stale belief is surfaced, never
  silently trusted.
* :meth:`persist` writes EXACTLY the phase's declared ``write_layers``. The
  policy's ``require_approval`` (optionally forced on by the runner via
  ``approval_required``) maps onto the NATIVE ``MemoryRecord`` lifecycle:

  ===================  =========================  ===================
  require_approval     lifecycle                  status
  ===================  =========================  ===================
  ``False``            ``MemoryLifecycle.ACTIVE`` ``MemoryStatus.ACTIVE``
  ``True``             ``MemoryLifecycle.CANDIDATE`` ``MemoryStatus.STALE``
  ===================  =========================  ===================

  There is no literal ``needs_review`` value in the native store; a
  ``candidate`` + ``stale`` record IS the persisted-but-needs-review state and is
  never dropped.

Port surface: recall uses ONLY the real
:class:`opencontext_core.memory.agent.AgentMemoryStore` port —
``store.search(query, scope=layer, limit=...)``. Durable writes route through
:class:`opencontext_core.memory.harness.MemoryHarness` (``harness.write(record)``),
the single sanctioned durable writer (book OC-MEMORY-001 §8/§10, enforced by the
``no-direct-memory-writes`` fitness guard) — so every phase record still gets the
conflict-check + KG-link tail. This gateway deliberately does NOT reuse
:class:`~opencontext_core.memory.capture.MemoryCaptureService`, whose ``capture()``
calls ``store.store(...)`` — a method the real store does not expose (the real
writer surface is ``write``).

Safety ("todo funcione sí o sí"): an unknown phase name is a no-op, a ``None`` /
``NullAgentMemoryStore`` backend is a no-op, and any store exception is swallowed
so a memory hiccup can never block the phase (memory is optional).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from opencontext_core.memory.phase_policy import PHASE_MEMORY_POLICY, PhaseMemoryPolicy
from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryLifecycle,
    MemoryRecord,
    MemoryStatus,
)

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PhaseOutcome:
    """What a phase produced, reduced to what the gateway needs to persist.

    ``content`` is the prose payload stored into each write layer; ``failed`` is
    True when the phase's gate status was FAILED (drives the recent-failure
    record so a future run's failure boost can activate).
    """

    content: str
    failed: bool = False


@dataclass
class RecallResult:
    """Partitioned recall: ``trusted`` (active) vs ``needs_review`` (candidate/stale)."""

    trusted: list[MemoryRecord] = field(default_factory=list)
    needs_review: list[MemoryRecord] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.trusted and not self.needs_review

    def render(self) -> str:
        """Render a compact prompt block. Needs-review context is flagged as stale.

        Empty string when nothing was recalled, so callers can append it
        unconditionally without introducing blank sections.
        """
        if self.is_empty():
            return ""
        lines: list[str] = ["## Recalled memory"]
        if self.trusted:
            lines.append("### Trusted")
            for rec in self.trusted:
                lines.append(f"- [{rec.layer.value}] {rec.content}")
        if self.needs_review:
            lines.append("### Needs review (stale — verify before relying on it)")
            for rec in self.needs_review:
                lines.append(f"- [{rec.layer.value}] {rec.content}")
        return "\n".join(lines)


def _is_null_store(store: Any) -> bool:
    """True when the backend is absent or the explicit Null object.

    A ``None`` store and a :class:`NullAgentMemoryStore` are both treated as
    "memory disabled" — the gateway no-ops rather than raising.
    """
    if store is None:
        return True
    # Import here to avoid a hard import cycle at module load and to keep the
    # gateway usable with any duck-typed store in tests.
    from opencontext_core.memory.agent import NullAgentMemoryStore

    return isinstance(store, NullAgentMemoryStore)


class PhaseMemoryGateway:
    """Shared recall/persist/lifecycle service for the SDD harness phase loop."""

    def __init__(self, store: Any, *, approval_required: bool = False) -> None:
        self._store = store
        self._approval_required = approval_required
        self._null = _is_null_store(store)
        # Durable writes go through the sole sanctioned writer (AVH-002). Built
        # lazily only when a real store is present; a Null/absent store persists
        # nothing so no harness is needed.
        self._harness: Any = None
        if not self._null:
            try:
                from opencontext_core.memory.harness import MemoryHarness

                self._harness = MemoryHarness(store)
            except Exception as exc:  # pragma: no cover - defensive; memory is optional
                _log.debug("phase-gateway harness construction failed: %s", exc)
                self._harness = None

    # -- factory ---------------------------------------------------------------

    @staticmethod
    def outcome(*, content: str, failed: bool = False) -> PhaseOutcome:
        """Build a :class:`PhaseOutcome` (convenience so callers need no extra import)."""
        return PhaseOutcome(content=content, failed=failed)

    # -- recall ----------------------------------------------------------------

    def recall(self, phase: str, query: str, limit: int = 5) -> RecallResult:
        """Search this phase's declared read layers and partition the hits.

        Unknown phase → empty result with ZERO searches. Null/absent store →
        empty result. Any store error is swallowed (memory is optional).
        """
        result = RecallResult()
        policy = PHASE_MEMORY_POLICY.get(phase)
        if policy is None or self._null:
            return result

        seen: set[str] = set()
        for layer in policy.read_layers:
            try:
                hits = self._store.search(query, scope=layer, limit=limit)
            except Exception as exc:  # pragma: no cover - defensive; memory is optional
                _log.debug("phase-recall search failed (phase=%s layer=%s): %s", phase, layer, exc)
                continue
            for rec in hits or []:
                rid = getattr(rec, "id", None)
                if rid is not None and rid in seen:
                    continue
                if rid is not None:
                    seen.add(rid)
                if self._is_trusted(rec):
                    result.trusted.append(rec)
                else:
                    result.needs_review.append(rec)
        return result

    @staticmethod
    def _is_trusted(rec: MemoryRecord) -> bool:
        """A record is trusted only when both axes say so: active lifecycle + active status."""
        return (
            getattr(rec, "lifecycle", None) == MemoryLifecycle.ACTIVE
            and getattr(rec, "status", None) == MemoryStatus.ACTIVE
        )

    # -- persist ---------------------------------------------------------------

    def persist(self, phase: str, outcome: PhaseOutcome) -> list[str]:
        """Write one record per declared write layer for this phase.

        Returns the list of written record ids (receipts). Unknown phase →
        no write. Null/absent store → no write. Store errors are swallowed.

        A FAILED outcome always lands a FAILURE-layer record even if the phase's
        declared write layers omit it, so the recent-failure boost can activate.
        """
        receipts: list[str] = []
        policy = PHASE_MEMORY_POLICY.get(phase)
        if policy is None or self._null or self._harness is None:
            return receipts

        write_layers = list(policy.write_layers)
        if outcome.failed and MemoryLayer.FAILURE not in write_layers:
            write_layers.append(MemoryLayer.FAILURE)

        lifecycle, status = self._lifecycle_for(policy)
        now = datetime.now(tz=UTC)
        for layer in write_layers:
            record = MemoryRecord(
                id=f"phase:{phase}:{layer.value}:{now.timestamp():.6f}",
                layer=layer,
                key=f"phase:{phase}",
                content=outcome.content,
                decay_policy=DecayPolicy(enabled=False),
                created_at=now,
                updated_at=now,
                provenance="agent",
                lifecycle=lifecycle,
                status=status,
                structured={"phase": phase, "failed": outcome.failed},
            )
            try:
                # Route through the sole sanctioned durable writer (AVH-002):
                # conflict-check + the one store.write + KG-link, returns a receipt.
                receipt = self._harness.write(record)
            except Exception as exc:  # pragma: no cover - defensive; memory is optional
                _log.debug("phase-persist write failed (phase=%s layer=%s): %s", phase, layer, exc)
                continue
            receipts.append(getattr(receipt, "memory_id", "") or record.id)
        return receipts

    def _lifecycle_for(self, policy: PhaseMemoryPolicy) -> tuple[MemoryLifecycle, MemoryStatus]:
        """Map require_approval (policy OR runner-forced) onto native lifecycle/status."""
        needs_approval = policy.require_approval or self._approval_required
        if needs_approval:
            return MemoryLifecycle.CANDIDATE, MemoryStatus.STALE
        return MemoryLifecycle.ACTIVE, MemoryStatus.ACTIVE
