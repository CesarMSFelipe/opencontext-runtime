"""AI-evaluation harness for personas / skills / harnesses (REL-14, OC-EVALS-001).

Runs eval suites over the PR-006 registries and writes immutable
:class:`EvaluationRecord`s carrying the book metric set, then diffs records across
releases (``eval compare``) flagging regressions.

HONESTY (build-rule #1): the built-in ``structural_scorer`` only measures what it
can verify WITHOUT a live model run — the structural validity of a definition
(local_validation_pass_rate). It does NOT fabricate a ``success_rate``; that field
stays 0.0 until a real task-running scorer is injected. The record/compare/persist
machinery is fully real and exercised by the tests with injected metrics.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from opencontext_core.evaluation.models import EvaluationRecord

EVAL_DIR = ".opencontext/evaluations"

#: Metrics where a HIGHER value is better (a drop is a regression).
_HIGHER_BETTER = ("success_rate", "local_validation_pass_rate")
#: Metrics where a LOWER value is better (a rise is a regression).
_LOWER_BETTER = ("token_count", "latency_ms", "retries", "escalation_rate", "patch_size")


class MetricDelta(BaseModel):
    """One metric's change between two evaluation records."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    old: float
    new: float
    delta: float
    regressed: bool


# ── Scorers ──────────────────────────────────────────────────────────────────

#: A scorer maps (target_kind, definition) -> the measured book metric dict.
Scorer = Callable[[str, Any], dict[str, Any]]


def structural_scorer(target_kind: str, definition: Any) -> dict[str, Any]:
    """Honest structural score: fraction of structural invariants a def satisfies.

    Measures real, checkable facts (non-empty id, declared contracts, etc.) and
    reports them as ``local_validation_pass_rate``. ``success_rate`` is left 0.0 —
    it requires a live task run we are not performing (no fabrication).
    """

    def has(name: str) -> bool:
        return bool(getattr(definition, name, None))

    checks: list[bool] = [has("id")]
    if target_kind == "persona":
        checks.append(has("responsibility") or has("description"))
    elif target_kind == "skill":
        checks.append(has("category"))
        checks.append(has("outputs") or has("triggers"))
    elif target_kind == "harness":
        checks.append(has("gates") or has("default_mode"))
    passed = sum(1 for c in checks if c)
    return {
        "local_validation_pass_rate": passed / len(checks) if checks else 0.0,
        "success_rate": 0.0,
    }


@dataclass
class AIEvalHarness:
    """Runs persona/skill/harness eval suites and writes immutable records."""

    runtime_version: str = "v1"
    provider: str = "none"
    profile: str = "balanced"
    benchmark_version: str = "1.0.0"

    def record(self, target_kind: str, target_id: str, metrics: dict[str, Any]) -> EvaluationRecord:
        """Build one frozen :class:`EvaluationRecord` from measured metrics."""
        return EvaluationRecord(
            target_kind=target_kind,
            target_id=target_id,
            runtime_version=self.runtime_version,
            provider=self.provider,
            profile=self.profile,
            benchmark_version=self.benchmark_version,
            success_rate=float(metrics.get("success_rate", 0.0)),
            token_count=int(metrics.get("token_count", 0)),
            latency_ms=int(metrics.get("latency_ms", 0)),
            retries=int(metrics.get("retries", 0)),
            escalation_rate=float(metrics.get("escalation_rate", 0.0)),
            patch_size=int(metrics.get("patch_size", 0)),
            local_validation_pass_rate=float(metrics.get("local_validation_pass_rate", 0.0)),
            task=str(metrics.get("task", "")),
            repository=str(metrics.get("repository", "")),
            workflow=str(metrics.get("workflow", "")),
            receipts=list(metrics.get("receipts", [])),
        )

    def evaluate_registry(
        self, target_kind: str, registry: Any, *, scorer: Scorer = structural_scorer
    ) -> list[EvaluationRecord]:
        """Score every definition in a registry into immutable records."""
        records: list[EvaluationRecord] = []
        for definition in registry.list():
            metrics = scorer(target_kind, definition)
            records.append(self.record(target_kind, definition.id, metrics))
        return records


# ── Compare (REL-14 scenario 2) ──────────────────────────────────────────────


def compare_records(old: EvaluationRecord, new: EvaluationRecord) -> list[MetricDelta]:
    """Per-metric deltas between two records; ``regressed`` flags worse values."""
    deltas: list[MetricDelta] = []
    for metric in (*_HIGHER_BETTER, *_LOWER_BETTER):
        o = float(getattr(old, metric))
        n = float(getattr(new, metric))
        delta = n - o
        if metric in _HIGHER_BETTER:
            regressed = n < o
        else:
            regressed = n > o
        deltas.append(MetricDelta(metric=metric, old=o, new=n, delta=delta, regressed=regressed))
    return deltas


# ── Persistence (immutable JSON records) ─────────────────────────────────────


def save_record(record: EvaluationRecord, directory: str | Path = EVAL_DIR) -> Path:
    """Persist one immutable record; filename is content-stable per target."""
    dest = Path(directory)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{record.target_kind}-{record.target_id}.json"
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_records(directory: str | Path = EVAL_DIR) -> list[EvaluationRecord]:
    """Load all persisted evaluation records from a directory (or empty)."""
    dest = Path(directory)
    if not dest.is_dir():
        return []
    out: list[EvaluationRecord] = []
    for path in sorted(dest.glob("*.json")):
        try:
            out.append(EvaluationRecord.model_validate_json(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


__all__ = [
    "EVAL_DIR",
    "AIEvalHarness",
    "MetricDelta",
    "Scorer",
    "compare_records",
    "load_records",
    "save_record",
    "structural_scorer",
]
