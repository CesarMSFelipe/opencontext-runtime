"""Decision API sink — append-only Decision Log (doc 59 §Decision API).

The :class:`DecisionRecorder` implements the internal Decision API
(``record(decision) -> DecisionLogEntry``, ``log_for_run(run_id)``). It is the
Brain's *only* write affordance: the Brain is handed ``recorder.record`` as its
record sink and nothing else (doc 59 §Brain restrictions). The log extends — it
does not duplicate — the existing ``RunEnvelope.policy_decisions`` evidence: an
entry may carry a ``policy_ref`` linking a ``PolicyDecision.id`` instead of
re-modelling it (RB-011).

In-memory by default; pass ``path`` to also append each entry as a JSONL line
(append-only, never rewrites — RB-003). The contract is shared with PR-000.4
(Decision Log & Learning Loop), which consumes this log.

PR-000.4 extends this module with the per-selection ergonomics the Learning Loop
needs: :class:`SelectionKind` (the six runtime selection kinds — workflow /
profile / provider / skill / harness / context), :meth:`DecisionRecorder.record_selection`
/ :meth:`DecisionRecorder.ingest`, the flat decision-shaped accessors on
:class:`DecisionLogEntry`, and the CRITICAL no-chain-of-thought guard
(:func:`redact_chain_of_thought`) applied to every persisted rationale (SPEC
DL-007, book invariant §9.8). The PR-000.1 ``DecisionKind`` (eight Brain
selection kinds, ``runtime/decisions.py``) is unchanged; ``SelectionKind`` is the
PR-000.4 decision-log vocabulary keyed to the six convergence selection kinds.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC, StrEnum
from opencontext_core.policy.memory_content import forbidden_memory_content
from opencontext_core.runtime.decisions import RuntimeDecision

# Durable-summary cap for a redacted rationale (no chain-of-thought, no dumps).
_MAX_RATIONALE_CHARS = 280
# Placeholder MUST itself be free of the forbidden markers it stands in for.
_REDACTED_PLACEHOLDER = "[redacted]"
_THINKING_BLOCK = re.compile(r"<thinking>.*?</thinking>", re.IGNORECASE | re.DOTALL)
_THINKING_TAG = re.compile(r"</?thinking>", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def redact_chain_of_thought(text: str) -> str:
    """Reduce *text* to a durable, decision-shaped summary — never chain-of-thought.

    CRITICAL INVARIANT (SPEC DL-007, book §9.8): the Decision Log and Learning
    Loop must never persist model chain-of-thought or raw scratch reasoning. This
    reuses the canonical marker scan (``policy.memory_content.forbidden_memory_content``)
    so the rule stays in one place. Durable facts/decisions pass through unchanged;
    text carrying reasoning/log markers is reduced to its marker-free segments
    (capped), and if nothing safe survives a stable placeholder is returned. The
    result is *guaranteed* to be free of the forbidden markers.
    """
    if not text or forbidden_memory_content(text) is None:
        return text
    # Drop whole ``<thinking>…</thinking>`` blocks (pure CoT) first so durable text
    # fused to a closing tag is not lost, then drop any remaining marker segments.
    stripped = _THINKING_TAG.sub(" ", _THINKING_BLOCK.sub(" ", text))
    segments = re.split(r"[\n.;]+", stripped)
    kept = [
        seg.strip() for seg in segments if seg.strip() and forbidden_memory_content(seg) is None
    ]
    summary = re.sub(r"\s+", " ", ". ".join(kept)).strip()[:_MAX_RATIONALE_CHARS].strip()
    if not summary or forbidden_memory_content(summary) is not None:
        return _REDACTED_PLACEHOLDER
    return summary


class SelectionKind(StrEnum):
    """The six runtime selection kinds the Decision Log records (convergence §5).

    Distinct from the PR-000.1 :class:`~opencontext_core.runtime.decisions.DecisionKind`
    (the eight Brain-selection kinds), which this PR does not own. These are the
    six selection points the Learning Loop reasons about: *why* the runtime chose
    a workflow / profile / provider / skill / harness / context.
    """

    workflow = "workflow"
    profile = "profile"
    provider = "provider"
    skill = "skill"
    harness = "harness"
    context = "context"


def _harden_decision(decision: RuntimeDecision) -> RuntimeDecision:
    """Return *decision* with its rationale redacted of chain-of-thought (DL-007)."""
    safe = redact_chain_of_thought(decision.reason)
    if safe == decision.reason:
        return decision
    return decision.model_copy(update={"reason": safe})


class DecisionLogEntry(BaseModel):
    """One append-only Decision Log entry: a decision plus optional evidence link.

    Wraps a typed :class:`RuntimeDecision` (PR-000.1, the canonical record) and
    adds the per-run learning fields (``evidence_refs``/``cost_estimate``/
    ``trace_id``). The flat ``entry_id``/``run_id``/``decision_kind``/``selected``/
    ``rationale``/``confidence``/``alternatives``/``created_at`` accessors project
    the wrapped decision so the Learning Loop and (later) Studio can read an entry
    without unwrapping it (SPEC DL-001/DL-002).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.decision_log_entry.v1"
    decision: RuntimeDecision
    # Links an existing ``RunEnvelope.PolicyDecision.id`` — no copy (RB-011).
    policy_ref: str | None = None
    # Learning-loop evidence (PR-000.4) — defaulted so the PR-000.1 ctor is unchanged.
    evidence_refs: list[str] = Field(default_factory=list)
    cost_estimate: dict[str, float] = Field(default_factory=dict)
    # References ``models.trace.RuntimeTrace`` for replay (DL-013); never copies events.
    trace_id: str | None = None
    recorded_at: str = Field(default_factory=_now_iso)

    @property
    def entry_id(self) -> str:
        """Stable id of this entry (the wrapped decision's id)."""
        return self.decision.decision_id

    @property
    def run_id(self) -> str | None:
        """Run the decision belongs to."""
        return self.decision.run_id

    @property
    def decision_kind(self) -> str:
        """The selection kind (``SelectionKind`` value or a legacy label)."""
        return self.decision.kind

    @property
    def selected(self) -> str:
        """The chosen option."""
        return self.decision.selected

    @property
    def alternatives(self) -> list[str]:
        """The rejected options."""
        return list(self.decision.alternatives)

    @property
    def rationale(self) -> str:
        """Durable, decision-shaped reason (redacted — never chain-of-thought)."""
        return self.decision.rationale

    @property
    def confidence(self) -> float:
        """Recorded selection confidence."""
        return self.decision.confidence

    @property
    def created_at(self) -> str:
        """When the entry was recorded."""
        return self.recorded_at


class DecisionRecorder:
    """Append-only sink implementing the internal Decision API.

    The Brain receives :meth:`record` as its sink. ``log_for_run`` and
    :meth:`entries` are read accessors used by the CLI/MCP inspection (RB-009).
    PR-000.4 adds :meth:`record_selection` (record a decision by kind/selected)
    and :meth:`ingest` (consume a PR-000.1 :class:`RuntimeDecision`); both share
    the one append-only persistence path and the no-CoT guard.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._entries: list[DecisionLogEntry] = []

    def record(
        self,
        decision: RuntimeDecision,
        *,
        policy_ref: str | None = None,
        evidence_refs: list[str] | None = None,
        cost_estimate: dict[str, float] | None = None,
        trace_id: str | None = None,
    ) -> DecisionLogEntry:
        """Append one entry per decision and return it (never rewrites priors).

        The rationale is passed through the no-CoT guard before persistence so no
        chain-of-thought ever lands in the log (SPEC DL-007).
        """
        entry = DecisionLogEntry(
            decision=_harden_decision(decision),
            policy_ref=policy_ref,
            evidence_refs=list(evidence_refs or []),
            cost_estimate=dict(cost_estimate or {}),
            trace_id=trace_id,
        )
        self.append(entry)
        return entry

    def append(self, entry: DecisionLogEntry) -> DecisionLogEntry:
        """Append a pre-built entry (append-only; mirrors persistence of record)."""
        self._entries.append(entry)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(entry.model_dump_json() + "\n")
        return entry

    def ingest(self, runtime_decision: RuntimeDecision, **kwargs: Any) -> DecisionLogEntry:
        """Ingest a PR-000.1 :class:`RuntimeDecision` into the log (DL-002)."""
        return self.record(runtime_decision, **kwargs)

    def record_selection(
        self,
        *,
        decision_kind: SelectionKind | str,
        selected: str,
        alternatives: list[str] | None = None,
        rationale: str = "",
        confidence: float = 0.5,
        run_id: str = "",
        evidence_refs: list[str] | None = None,
        cost_estimate: dict[str, float] | None = None,
        trace_id: str | None = None,
        policy_ref: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> DecisionLogEntry:
        """Record *why* a runtime selection was made, by kind (SPEC DL-002).

        Builds a typed :class:`RuntimeDecision` and records it; the rationale is
        redacted of chain-of-thought by :meth:`record`.
        """
        decision = RuntimeDecision(
            kind=str(decision_kind),
            chosen=selected,
            reason=rationale,
            alternatives=list(alternatives or []),
            confidence=confidence,
            run_id=run_id or None,
            inputs=dict(inputs or {}),
        )
        return self.record(
            decision,
            policy_ref=policy_ref,
            evidence_refs=evidence_refs,
            cost_estimate=cost_estimate,
            trace_id=trace_id,
        )

    def entries(self) -> list[DecisionLogEntry]:
        """Return every recorded entry, in append order."""
        return list(self._entries)

    def log_for_run(self, run_id: str) -> list[DecisionLogEntry]:
        """Return the entries whose decision belongs to *run_id* (in order)."""
        return [e for e in self._entries if e.decision.run_id == run_id]

    def __len__(self) -> int:
        return len(self._entries)


__all__ = [
    "DecisionLogEntry",
    "DecisionRecorder",
    "SelectionKind",
    "redact_chain_of_thought",
]
