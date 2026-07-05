"""ImprovementProposal — write-only, never auto-applied (PR-000.4 / SPEC DL-004).

The honesty boundary (OC-FINAL §9.8, [[oc-value-eval-2026-06]]): an
``ImprovementProposal`` is a propose-only record. ``write()`` appends it
to the Decision Log without mutating any target. ``apply()`` requires
explicit human approval — public, builtin, and internal targets alike
raise :class:`ApprovalRequired` until an approver is recorded. The
proposal API exposes no auto_apply path by design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ApprovalRequired(Exception):
    """Raised when ``apply()`` is called without an explicit human approval."""


_APPROVAL_REQUIRED_MSG = "human_approval_missing"


@dataclass
class ImprovementProposal:
    """A propose-only improvement record.

    ``approval`` is the human approver id, or ``None`` for unapproved.
    ``status`` starts as ``"proposed"`` and only advances to ``"applied"``
    via an explicit, approval-bearing :meth:`apply` call.
    """

    proposal_id: str
    title: str
    rationale: str
    target_type: str
    approval: str | None = None
    status: str = "proposed"
    payload: dict[str, Any] = field(default_factory=dict)

    def write(self, *, target: Any, decision_log: Any, applied: bool) -> None:
        """Append this proposal to *decision_log* WITHOUT mutating *target*.

        ``applied`` is the caller-asserted invariant — the proposal layer
        never flips it; the assertion belongs to the policy enforcer.
        """
        record = {
            "proposal_id": self.proposal_id,
            "title": self.title,
            "rationale": self.rationale,
            "target_type": self.target_type,
            "approval": self.approval,
            "status": self.status,
            "applied": bool(applied),
        }
        if hasattr(decision_log, "append"):
            decision_log.append(record)
        elif isinstance(decision_log, dict):
            decision_log.setdefault("writes", []).append(record)
        else:
            raise TypeError(
                f"decision_log must be list-like or dict-like, got {type(decision_log).__name__}"
            )
        # Invariant: write() must never mutate target (SPEC DL-004).
        # The presence of ``target`` in the signature is forward-looking; today
        # no mutation happens, by construction.

    def apply(self, *, decision_log: Any | None = None) -> None:
        """Apply this proposal — requires an explicit human approval.

        Raises :class:`ApprovalRequired` if no approver is recorded.
        On success, marks ``status='applied'`` and appends an ``applied``
        event to *decision_log* (if provided).
        """
        if not (self.approval and str(self.approval).strip()):
            raise ApprovalRequired(_APPROVAL_REQUIRED_MSG)

        self.status = "applied"
        if decision_log is not None:
            record = {
                "proposal_id": self.proposal_id,
                "event": "applied",
                "approval": self.approval,
                "target_type": self.target_type,
            }
            if hasattr(decision_log, "append"):
                decision_log.append(record)
            elif isinstance(decision_log, dict):
                decision_log.setdefault("applies", []).append(record)
            else:
                msg = (
                    f"decision_log must be list-like or dict-like, "
                    f"got {type(decision_log).__name__}"
                )
                raise TypeError(msg)


__all__ = [
    "ApprovalRequired",
    "ImprovementProposal",
]
