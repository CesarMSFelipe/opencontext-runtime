"""Persisted quality baseline snapshot + ratchet diff.

``BaselineStore`` writes a metrics+findings snapshot to
``.opencontext/quality-baseline.json`` and diffs the current findings against it
so the gate can report ONLY the new violations (the ratchet). The diff key is the
SHARED :func:`opencontext_core.quality.models.finding_key` — this module never
reimplements it, so the save key and the diff key can never disagree.

Design invariants:

* The bucket choice (symbol preferred over line) lives in exactly one place,
  :meth:`BaselineStore.key_for`, reused by both ``save`` and ``diff``.
* ``score`` is the integer ``HealthScore.score`` captured at snapshot time so the
  baseline round-trips through JSON losslessly.
* The write is atomic (temp file + ``os.replace``) so the baseline is never left
  half-written; the read is tolerant (a missing or old-schema file yields
  ``None`` rather than raising) so a stale baseline degrades honestly.

Deterministic, stdlib ``json`` only, zero model calls.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from opencontext_core.quality.models import Finding, HealthScore, QualityMetrics, finding_key


@dataclass(frozen=True)
class Baseline:
    """An immutable snapshot of the quality state at capture time.

    ``keys`` is the set of :func:`finding_key` values for every recorded finding;
    a current finding whose key is absent from this set is a NEW violation.
    """

    keys: frozenset[str]  # finding_key for every recorded finding
    metrics: QualityMetrics
    score: int  # HealthScore.score at capture time
    generated_at: str

    def diff(self, current: tuple[Finding, ...]) -> tuple[Finding, ...]:
        """Return the findings whose key is NOT in this baseline (the new ones).

        The bucket (symbol or line) is resolved through the same
        :meth:`BaselineStore.key_for` helper the snapshot used, so a finding that
        existed at capture time is matched and suppressed, while a genuinely new
        finding (new file/line/symbol or new rule) passes through.
        """
        new: list[Finding] = []
        for f in current:
            if BaselineStore.key_for(f) not in self.keys:
                new.append(f)
        return tuple(new)


class BaselineStore:
    """Load/save/diff the quality baseline JSON for one project root."""

    # Schema version stamped into the file; bumping it invalidates old baselines
    # (load returns None on an unrecognized version -> a fresh snapshot is taken).
    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        """``path`` is ``root / rules.baseline_path`` (the baseline JSON file)."""
        self.path = Path(path)

    def exists(self) -> bool:
        """True if the baseline file is present on disk."""
        return self.path.is_file()

    def load(self) -> Baseline | None:
        """Read and parse the baseline JSON; ``None`` if absent or unusable.

        Tolerant by design: a missing file, malformed JSON, a wrong/old schema
        version, or a structurally invalid payload all return ``None`` rather
        than raising, so the gate falls back to taking a fresh snapshot and never
        crashes on a stale or corrupt baseline.
        """
        if not self.path.is_file():
            return None
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        # Reject an unrecognized schema version (treat as "no baseline").
        version = data.get("version")
        if version is not None and version != self.SCHEMA_VERSION:
            return None

        findings = data.get("findings")
        if not isinstance(findings, list):
            return None
        keys: set[str] = set()
        for row in findings:
            if isinstance(row, dict):
                key = row.get("key")
                if isinstance(key, str) and key:
                    keys.add(key)

        metrics_raw = data.get("metrics")
        metrics = (
            QualityMetrics.from_dict(metrics_raw)
            if isinstance(metrics_raw, dict)
            else QualityMetrics()
        )

        score_raw = data.get("score", 0)
        try:
            score = int(score_raw)
        except (TypeError, ValueError):
            score = 0

        generated_at = data.get("generated_at")
        if not isinstance(generated_at, str):
            generated_at = ""

        return Baseline(
            keys=frozenset(keys),
            metrics=metrics,
            score=score,
            generated_at=generated_at,
        )

    def save(
        self,
        findings: tuple[Finding, ...],
        metrics: QualityMetrics,
        health: HealthScore,
    ) -> Baseline:
        """Persist a snapshot atomically and return the :class:`Baseline`.

        Writes ``{version, generated_at, score, metrics, findings:[{key, file,
        rule, severity, symbol_or_line}]}``. The parent directory is created if
        needed. The write is atomic: a sibling temp file is written then
        ``os.replace``-d over the target, so a reader never observes a partial
        file. The returned ``Baseline`` reflects exactly what was written.
        """
        rows: list[dict[str, object]] = []
        keys: set[str] = set()
        for f in findings:
            key = self.key_for(f)
            keys.add(key)
            rows.append(
                {
                    "key": key,
                    "rule": f.rule,
                    "severity": f.severity.value,
                    "file": f.file,
                    "symbol_or_line": self._bucket(f),
                }
            )

        generated_at = datetime.now(UTC).isoformat()
        payload = {
            "version": self.SCHEMA_VERSION,
            "generated_at": generated_at,
            "score": int(health.score),
            "metrics": metrics.as_dict(),
            "findings": rows,
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)

        return Baseline(
            keys=frozenset(keys),
            metrics=metrics,
            score=int(health.score),
            generated_at=generated_at,
        )

    @staticmethod
    def _bucket(f: Finding) -> str | int | None:
        """The symbol-or-line bucket value: symbol when present, else line.

        SINGLE definition of the bucket choice so ``save`` and ``diff`` agree.
        """
        return f.symbol if f.symbol else f.line

    @staticmethod
    def key_for(f: Finding) -> str:
        """Ratchet key for a finding via the shared :func:`finding_key`.

        Thin wrapper: ``finding_key(f.rule, f.file, symbol or line)``. This is the
        ONLY place the bucket choice is applied, reused by both save and diff so
        the keys always match.
        """
        return finding_key(f.rule, f.file, BaselineStore._bucket(f))
