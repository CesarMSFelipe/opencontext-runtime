"""Append-only, deterministic per-evaluation quality evolution log.

``EvolutionStore`` records one ``{timestamp, score, sub_scores}`` row per
evaluation to ``.opencontext/quality-evolution.json`` and returns the
:class:`EvolutionTrend` (latest / previous / delta / count + full history) so a
caller can surface how the rolled-up health score is moving across runs. The
``runs/<id>/run.json`` history plus this file together ARE the cross-run
evolution record.

Design invariants:

* The CALLER injects every timestamp (a run's ``created_at`` / ISO string). This
  module NEVER reads a wall clock and NEVER generates a random id — so it is
  fully deterministic and testable, and identical inputs yield a byte-identical
  file (``sort_keys`` + caller-supplied timestamp).
* Reads are tolerant (a missing, corrupt, or non-list file yields an empty
  history rather than raising) so a stale or hand-edited log degrades honestly —
  the same posture as :meth:`opencontext_core.quality.baseline.BaselineStore.load`.
* The write is atomic (sibling temp file + ``os.replace``) so a reader never
  observes a half-written list; the parent directory is created on demand.
* No score math lives here. Evolution only RECORDS what
  :func:`opencontext_core.quality.evaluator.QualityEvaluator.compute_health`
  already produced (see :func:`entry_from_health`).

Stdlib ``json`` only, ZERO model calls, ZERO subprocess.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from opencontext_core.quality.models import HealthScore

# Canonical, project-relative location of the evolution log. The runner builds
# the absolute path as ``root / EVOLUTION_FILENAME``.
EVOLUTION_FILENAME = ".opencontext/quality-evolution.json"


@dataclass(frozen=True)
class EvolutionEntry:
    """One recorded evaluation: the rolled-up score + its per-signal breakdown.

    ``timestamp`` is the caller-supplied value (a run's ``created_at`` / ISO
    string) — NEVER generated inside this module. ``sub_scores`` mirrors
    :attr:`opencontext_core.quality.models.HealthScore.components` (the
    per-signal penalty breakdown) so the trend can explain WHY the score moved.
    """

    timestamp: str  # caller-supplied (run created_at / ISO string); never generated here
    score: int  # HealthScore.score at that evaluation
    sub_scores: dict[str, int]  # == HealthScore.components (per-signal penalties)


@dataclass(frozen=True)
class EvolutionTrend:
    """The recomputed trend over the recorded history (the surfacing surface).

    For fewer than two entries the trend degrades gracefully: ``previous`` equals
    ``latest`` and ``delta`` is 0, so a first-ever run reports a flat trend rather
    than a spurious swing.
    """

    latest: int  # score of the last entry (0 when empty)
    previous: int  # score of the entry before it (== latest when <2 entries)
    delta: int  # latest - previous (0 when <2 entries)
    count: int  # number of recorded entries
    history: tuple[EvolutionEntry, ...]


def _coerce_int(value: object, default: int = 0) -> int:
    """Coerce a JSON scalar to ``int`` (a float like ``60.0`` -> ``60``).

    Tolerant: a non-numeric value falls back to ``default`` so a single bad
    field never breaks the whole row.
    """
    if isinstance(value, bool):  # bool is an int subclass; treat as numeric
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _coerce_sub_scores(raw: object) -> dict[str, int]:
    """Coerce a ``sub_scores`` mapping to ``{str: int}`` (non-dict -> ``{}``)."""
    if not isinstance(raw, dict):
        return {}
    return {str(k): _coerce_int(v) for k, v in raw.items()}


class EvolutionStore:
    """Load / append / read the quality evolution log for one project root."""

    def __init__(self, path: Path) -> None:
        """``path`` is ``root / EVOLUTION_FILENAME`` (the evolution JSON file)."""
        self.path = Path(path)

    def append(self, *, timestamp: str, score: int, sub_scores: dict[str, int]) -> EvolutionTrend:
        """Append one evaluation row and return the recomputed trend.

        Reads the existing list tolerantly (a missing / corrupt / non-list file
        is treated as empty, exactly like :meth:`BaselineStore.load`), appends
        ``{timestamp, score, sub_scores}`` with ``score`` coerced to ``int`` and
        every ``sub_scores`` value coerced to ``int`` and sorted, then writes the
        WHOLE list back atomically (temp file + ``os.replace``, parents created)
        with ``json.dumps(..., indent=2, sort_keys=True)``. The timestamp is
        stored verbatim — never substituted with a wall-clock value.
        """
        rows = self._read_rows()
        rows.append(
            {
                "timestamp": str(timestamp),
                "score": _coerce_int(score),
                # dict(sorted(...)) so the persisted row is order-stable.
                "sub_scores": dict(sorted(_coerce_sub_scores(sub_scores).items())),
            }
        )
        self._write_rows(rows)
        return self._trend_from_rows(rows)

    def load(self) -> tuple[EvolutionEntry, ...]:
        """Parse the JSON array tolerantly into typed entries (chronological).

        Each row must carry a ``str`` timestamp, an ``int``-coercible score, and a
        ``dict`` ``sub_scores`` to be kept; a malformed row is skipped rather than
        raising. A missing or corrupt file, or a non-list payload, yields ``()``.
        Order is preserved as written (append order == chronological).
        """
        entries: list[EvolutionEntry] = []
        for row in self._read_rows():
            timestamp = row.get("timestamp")
            if not isinstance(timestamp, str):
                continue
            raw_score = row.get("score")
            # A missing/None or non-numeric score is a malformed row -> skip it.
            if not isinstance(raw_score, (int, float)) or isinstance(raw_score, bool):
                continue
            raw_sub = row.get("sub_scores")
            if not isinstance(raw_sub, dict):
                continue
            entries.append(
                EvolutionEntry(
                    timestamp=timestamp,
                    score=_coerce_int(raw_score),
                    sub_scores=_coerce_sub_scores(raw_sub),
                )
            )
        return tuple(entries)

    def trend(self) -> EvolutionTrend:
        """Build the :class:`EvolutionTrend` from :meth:`load` WITHOUT writing.

        This is the read path for surfacing the current trend/delta (e.g. into
        ``run.json`` metadata) without recording a new evaluation.
        """
        return self._trend_from_entries(self.load())

    # -- internals ---------------------------------------------------------- #

    def _read_rows(self) -> list[dict[str, object]]:
        """Read the raw JSON list tolerantly; ``[]`` on missing/corrupt/non-list."""
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        # Keep only dict rows; non-dict junk entries are dropped here so neither
        # load() nor the trend math has to defend against them again.
        return [row for row in data if isinstance(row, dict)]

    def _write_rows(self, rows: list[dict[str, object]]) -> None:
        """Atomically write the whole row list (temp file + ``os.replace``)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)

    def _trend_from_rows(self, rows: list[dict[str, object]]) -> EvolutionTrend:
        """Recompute the trend from raw rows (used by append, post-write)."""
        return self._trend_from_entries(self._entries_from_rows(rows))

    @staticmethod
    def _entries_from_rows(rows: list[dict[str, object]]) -> tuple[EvolutionEntry, ...]:
        """Typed entries from already-validated raw rows (append's own write)."""
        out: list[EvolutionEntry] = []
        for row in rows:
            timestamp = row.get("timestamp")
            raw_score = row.get("score")
            raw_sub = row.get("sub_scores")
            if not isinstance(timestamp, str):
                continue
            if not isinstance(raw_score, (int, float)) or isinstance(raw_score, bool):
                continue
            if not isinstance(raw_sub, dict):
                continue
            out.append(
                EvolutionEntry(
                    timestamp=timestamp,
                    score=_coerce_int(raw_score),
                    sub_scores=_coerce_sub_scores(raw_sub),
                )
            )
        return tuple(out)

    @staticmethod
    def _trend_from_entries(entries: tuple[EvolutionEntry, ...]) -> EvolutionTrend:
        """Derive latest / previous / delta / count from chronological entries."""
        count = len(entries)
        if count == 0:
            return EvolutionTrend(latest=0, previous=0, delta=0, count=0, history=())
        latest = entries[-1].score
        previous = entries[-2].score if count >= 2 else latest
        return EvolutionTrend(
            latest=latest,
            previous=previous,
            delta=latest - previous,
            count=count,
            history=entries,
        )


def entry_from_health(
    health: HealthScore, *, timestamp: str
) -> dict[str, int | str | dict[str, int]]:
    """Bridge a :class:`HealthScore` into an :meth:`EvolutionStore.append` payload.

    Maps ``health.score`` -> ``score`` and ``health.components`` -> ``sub_scores``
    (COPIED, not aliased, so a later mutation of the health map cannot corrupt an
    already-built row). The ``timestamp`` is the caller's injected value. No score
    math happens here — this only records what ``compute_health`` produced.
    """
    return {
        "timestamp": timestamp,
        "score": health.score,
        "sub_scores": dict(health.components),
    }
