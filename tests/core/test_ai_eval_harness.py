"""AI-evaluation harness: immutable records + compare + persistence (REL-14)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.evaluation.ai_eval import (
    AIEvalHarness,
    compare_records,
    load_records,
    save_record,
    structural_scorer,
)
from opencontext_core.evaluation.models import EvaluationRecord
from opencontext_core.personas import PersonaRegistry


def test_record_carries_the_book_metric_set() -> None:
    rec = AIEvalHarness(provider="ollama", profile="balanced").record(
        "harness",
        "mutation",
        {
            "success_rate": 0.9,
            "token_count": 1200,
            "latency_ms": 800,
            "retries": 1,
            "escalation_rate": 0.1,
            "patch_size": 30,
            "local_validation_pass_rate": 1.0,
            "benchmark_version": "1.0.0",
        },
    )
    assert isinstance(rec, EvaluationRecord)
    assert rec.schema_version == "opencontext.evaluation_record.v1"
    assert rec.success_rate == 0.9 and rec.token_count == 1200
    assert rec.local_validation_pass_rate == 1.0 and rec.provider == "ollama"


def test_structural_scorer_is_honest_about_success_rate() -> None:
    """The built-in scorer measures structure only; it never fabricates success."""
    registry = PersonaRegistry.with_builtins()
    records = AIEvalHarness().evaluate_registry("persona", registry, scorer=structural_scorer)
    assert records, "builtin persona registry should be non-empty"
    for rec in records:
        assert rec.target_kind == "persona"
        assert rec.local_validation_pass_rate > 0.0  # real structural measurement
        assert rec.success_rate == 0.0  # honest: no live task run performed


def test_compare_flags_regressions_per_metric() -> None:
    harness = AIEvalHarness()
    old = harness.record("skill", "x", {"success_rate": 0.9, "token_count": 100})
    new = harness.record("skill", "x", {"success_rate": 0.7, "token_count": 150})
    deltas = {d.metric: d for d in compare_records(old, new)}
    assert deltas["success_rate"].regressed is True  # lower is worse
    assert deltas["token_count"].regressed is True  # higher is worse
    # An improvement is not a regression.
    better = harness.record("skill", "x", {"success_rate": 0.95, "token_count": 80})
    deltas2 = {d.metric: d for d in compare_records(old, better)}
    assert deltas2["success_rate"].regressed is False
    assert deltas2["token_count"].regressed is False


def test_records_persist_and_reload(tmp_path: Path) -> None:
    rec = AIEvalHarness().record("harness", "tdd", {"local_validation_pass_rate": 1.0})
    path = save_record(rec, tmp_path)
    assert path.is_file()
    loaded = load_records(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].target_id == "tdd" and loaded[0].target_kind == "harness"
