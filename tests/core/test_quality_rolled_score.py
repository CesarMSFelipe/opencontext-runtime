"""Behavior tests for the Phase-3 rolled-up health score in ``evaluator.py``.

Phase 3 folds the two new :class:`QualityMetrics` depth signals — ``duplication``
(near-duplicate function pairs) and ``max_nesting`` (code block-nesting depth) —
into the SINGLE rolled-up :meth:`QualityEvaluator.compute_health` number, as two
additional bounded basis-point penalties beside the existing cycles / god-files /
coupling / complexity / boundary / directory-depth terms. The headline verdict
stays one integer (``HealthScore.score``), and the per-signal sub-scores are
surfaced through ``HealthScore.components`` -> ``QualityReport.health.components``
-> ``report['health']['components']`` end-to-end (no new ``QualityReport`` field).

These tests lock the contract that:

* the new ``duplication`` / ``nesting`` terms appear in ``components`` and lower
  the rolled-up score by the documented weights,
* each term is CAPPED + the total is CLAMPED to ``[0, PERFECT_SCORE]`` so neither
  a clone storm nor a deeply-nested function can dominate or underflow the score,
* nesting at/below ``NESTING_FREE`` costs nothing (soft knee), like ``depth``,
* a duplication/nesting regression makes ``current.score < baseline.score`` so the
  pre-existing ``evaluate_health_regression`` rule trips (FAILED under strict /
  WARNING otherwise) with no new code in that function,
* a real-source ``snapshot()`` over clones reflects the lower rolled-up score,
* the fold stays deterministic and integer-only.

Every test is ``tmp_path``-isolated (graph DB under ``tmp_path/.storage``, no
home/cwd config read) and makes ZERO model calls; the ``snapshot()`` cases also
make ZERO subprocesses (asserted via a monkeypatched ``subprocess.run`` boom).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.indexing.scanner import ScannedFile
from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser
from opencontext_core.models.project import FileKind
from opencontext_core.quality import languages as languages_mod
from opencontext_core.quality.ci_checks import CheckSeverity, CheckStatus
from opencontext_core.quality.evaluator import (
    _CAP_DUP,
    _CAP_NESTING,
    NESTING_FREE,
    PERFECT_SCORE,
    W_DUP,
    W_NESTING,
    QualityEvaluator,
)
from opencontext_core.quality.models import QualityMetrics
from opencontext_core.quality.rules import (
    DEFAULT_RULES,
    QualityMode,
    QualityRules,
)

_TREE_SITTER = TreeSitterParser()
requires_tree_sitter = pytest.mark.skipif(
    not (_TREE_SITTER.is_available() and "python" in _TREE_SITTER._languages),
    reason="tree-sitter python grammar not available",
)


# --------------------------------------------------------------------------- #
# fixtures / helpers (all tmp_path-isolated)
# --------------------------------------------------------------------------- #


def _empty_db(root: Path) -> Path:
    """Create an empty (schema-only) graph DB under ``root`` and return its path."""
    db_path = root / ".storage" / "opencontext" / "context_graph.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    db.close()
    return db_path


def _scanned(root: Path, rel: str, content: str) -> ScannedFile:
    """A minimal :class:`ScannedFile` for an in-repo source path."""
    return ScannedFile(
        path=root / rel,
        relative_path=rel,
        language="python",
        file_type=FileKind.CODE,
        content=content,
        tokens=max(1, len(content) // 4),
        size_bytes=len(content.encode("utf-8")),
        summary="",
        metadata={},
    )


# A substantial function body, well over the default 40-token clone floor, so two
# copies in different files are a real near-duplicate pair (not boilerplate).
_CLONE_BODY = (
    "def process_records(records, threshold, label):\n"
    "    total = 0\n"
    "    accepted = []\n"
    "    rejected = []\n"
    "    for record in records:\n"
    "        value = record.get('value', 0)\n"
    "        if value > threshold:\n"
    "            accepted.append((label, record, value))\n"
    "            total = total + value\n"
    "        else:\n"
    "            rejected.append((label, record))\n"
    "    summary = {'total': total, 'accepted': len(accepted)}\n"
    "    return accepted, rejected, summary\n"
)


def _deep_nested_source(depth: int) -> str:
    """A single function with ``depth`` levels of straight ``if`` nesting."""
    lines = ["def deeply(x):"]
    indent = "    "
    for level in range(depth):
        lines.append(f"{indent * (level + 1)}if x > {level}:")
    lines.append(f"{indent * (depth + 1)}return x")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# compute_health: the two new signals fold into the SINGLE rolled-up score
# (pure integer arithmetic — no graph / tree-sitter needed for these)
# --------------------------------------------------------------------------- #


def test_duplication_metric_lowers_the_rolled_up_score_by_weight() -> None:
    """Each near-duplicate pair subtracts exactly ``W_DUP`` from the headline score."""
    clean = QualityEvaluator.compute_health(QualityMetrics(), DEFAULT_RULES)
    dup = QualityEvaluator.compute_health(QualityMetrics(duplication=3), DEFAULT_RULES)
    assert clean.score == PERFECT_SCORE
    assert dup.components["duplication"] == W_DUP * 3
    assert dup.score == PERFECT_SCORE - (W_DUP * 3)


def test_nesting_metric_lowers_the_rolled_up_score_over_the_free_knee() -> None:
    """Code-nesting penalizes only the levels ABOVE ``NESTING_FREE`` (soft knee)."""
    over = QualityEvaluator.compute_health(
        QualityMetrics(max_nesting=NESTING_FREE + 2), DEFAULT_RULES
    )
    assert over.components["nesting"] == W_NESTING * 2
    assert over.score == PERFECT_SCORE - (W_NESTING * 2)


def test_nesting_at_or_below_free_knee_costs_nothing() -> None:
    """``max_nesting`` at/below ``NESTING_FREE`` contributes a zero penalty."""
    at = QualityEvaluator.compute_health(QualityMetrics(max_nesting=NESTING_FREE), DEFAULT_RULES)
    below = QualityEvaluator.compute_health(
        QualityMetrics(max_nesting=NESTING_FREE - 1), DEFAULT_RULES
    )
    assert at.components["nesting"] == 0
    assert at.score == PERFECT_SCORE
    assert below.components["nesting"] == 0
    assert below.score == PERFECT_SCORE


def test_components_always_carry_both_new_subscores() -> None:
    """The breakdown ALWAYS exposes 'duplication' and 'nesting' keys (the sub-score surface)."""
    h = QualityEvaluator.compute_health(QualityMetrics(), DEFAULT_RULES)
    assert "duplication" in h.components
    assert "nesting" in h.components
    # A perfectly-clean project still reports the keys, just at zero penalty.
    assert h.components["duplication"] == 0
    assert h.components["nesting"] == 0


def test_new_signals_combine_with_existing_terms_in_one_number() -> None:
    """Duplication + nesting add to the SAME rolled-up penalty as the legacy signals."""
    from opencontext_core.quality.evaluator import W_CYCLES, W_GOD

    m = QualityMetrics(
        cycles=1,
        god_files=1,
        duplication=2,
        max_nesting=NESTING_FREE + 3,
    )
    h = QualityEvaluator.compute_health(m, DEFAULT_RULES)
    expected_penalty = (W_CYCLES * 1) + (W_GOD * 1) + (W_DUP * 2) + (W_NESTING * 3)
    # The headline verdict is a single int that already includes the new signals.
    assert isinstance(h.score, int)
    assert h.score == PERFECT_SCORE - expected_penalty


def test_duplication_and_nesting_terms_are_capped() -> None:
    """A huge clone/nesting count cannot exceed its per-signal cap (no domination)."""
    huge = QualityEvaluator.compute_health(
        QualityMetrics(duplication=10_000, max_nesting=10_000), DEFAULT_RULES
    )
    # Each term is bounded at its cap * weight, never count * weight.
    assert huge.components["duplication"] == W_DUP * _CAP_DUP
    assert huge.components["nesting"] == W_NESTING * _CAP_NESTING


def test_rolled_up_score_clamped_to_zero_under_a_clone_storm() -> None:
    """Even pathological duplication/nesting can never push the score below 0."""
    h = QualityEvaluator.compute_health(
        QualityMetrics(duplication=10_000, max_nesting=10_000), DEFAULT_RULES
    )
    assert 0 <= h.score <= PERFECT_SCORE
    # Combined with every other signal maxed out it still floors at 0, not negative.
    everything = QualityEvaluator.compute_health(
        QualityMetrics(
            cycles=10_000,
            god_files=10_000,
            max_cc=10_000,
            max_in_degree=10_000,
            boundary_violations=10_000,
            max_depth=10_000,
            duplication=10_000,
            max_nesting=10_000,
        ),
        DEFAULT_RULES,
    )
    assert everything.score == 0


def test_a_single_new_signal_cannot_dominate_below_zero() -> None:
    """Duplication alone, even capped, leaves the score positive (bounded term)."""
    only_dup = QualityEvaluator.compute_health(QualityMetrics(duplication=10_000), DEFAULT_RULES)
    # Capped duplication penalty is small relative to PERFECT_SCORE.
    assert only_dup.score == PERFECT_SCORE - (W_DUP * _CAP_DUP)
    assert only_dup.score > 0


def test_rolled_up_fold_is_deterministic() -> None:
    """Identical metrics -> identical rolled-up HealthScore (integer-exact, stable keys)."""
    m = QualityMetrics(duplication=2, max_nesting=NESTING_FREE + 4)
    first = QualityEvaluator.compute_health(m, DEFAULT_RULES)
    second = QualityEvaluator.compute_health(m, DEFAULT_RULES)
    assert first == second
    assert first.components == second.components


# --------------------------------------------------------------------------- #
# regression: a duplication/nesting increase trips the EXISTING health rule
# (no new code in evaluate_health_regression — the new signal rides the score)
# --------------------------------------------------------------------------- #


def test_duplication_regression_lowers_score_vs_baseline(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    ev = QualityEvaluator(tmp_path, rules=DEFAULT_RULES, scanned_files=[])
    baseline = QualityEvaluator.compute_health(QualityMetrics(), DEFAULT_RULES)
    current = QualityEvaluator.compute_health(QualityMetrics(duplication=1), DEFAULT_RULES)
    assert current.score < baseline.score
    verdict = ev.evaluate_health_regression(
        baseline, current, QualityRules(mode=QualityMode.STRICT)
    )
    assert verdict.status == CheckStatus.FAILED
    assert verdict.severity == CheckSeverity.ERROR


def test_nesting_regression_warns_under_ratchet(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    ev = QualityEvaluator(tmp_path, rules=DEFAULT_RULES, scanned_files=[])
    baseline = QualityEvaluator.compute_health(
        QualityMetrics(max_nesting=NESTING_FREE), DEFAULT_RULES
    )
    current = QualityEvaluator.compute_health(
        QualityMetrics(max_nesting=NESTING_FREE + 3), DEFAULT_RULES
    )
    assert current.score < baseline.score
    verdict = ev.evaluate_health_regression(
        baseline, current, QualityRules(mode=QualityMode.RATCHET)
    )
    assert verdict.status == CheckStatus.FAILED
    assert verdict.severity == CheckSeverity.WARNING


def test_status_fails_strict_when_new_signal_drops_the_score(tmp_path: Path) -> None:
    """A finding-free change still FAILS under strict if duplication dropped the score."""
    _empty_db(tmp_path)
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.STRICT), scanned_files=[])
    baseline = QualityEvaluator.compute_health(QualityMetrics(), DEFAULT_RULES)
    lowered = QualityEvaluator.compute_health(QualityMetrics(duplication=1), DEFAULT_RULES)
    from opencontext_core.harness.models import GateStatus

    status = ev._status((), lowered, baseline)
    assert status == GateStatus.FAILED


# --------------------------------------------------------------------------- #
# end-to-end surfacing: sub-scores ride through QualityReport + report dict
# --------------------------------------------------------------------------- #


@requires_tree_sitter
def test_snapshot_over_clones_reflects_a_lower_rolled_up_score(tmp_path: Path, monkeypatch) -> None:
    """A real-source snapshot with a clone pair reports a lower SINGLE score + dup sub-score."""

    def _boom(*_a, **_k):  # pragma: no cover - only fires on a regression
        raise AssertionError("snapshot must not spawn subprocesses")

    monkeypatch.setattr(languages_mod.subprocess, "run", _boom)

    _empty_db(tmp_path)
    clean = QualityEvaluator(
        tmp_path,
        rules=DEFAULT_RULES,
        scanned_files=[_scanned(tmp_path, "ok.py", "def f():\n    return 1\n")],
    ).snapshot()

    cloned = QualityEvaluator(
        tmp_path,
        rules=DEFAULT_RULES,
        scanned_files=[
            _scanned(tmp_path, "a.py", _CLONE_BODY),
            _scanned(tmp_path, "b.py", _CLONE_BODY),
        ],
    ).snapshot()

    assert clean.score == PERFECT_SCORE
    # The clone pair is reflected in BOTH the metric and the rolled-up score.
    assert cloned.metrics.duplication >= 1
    assert cloned.components["duplication"] >= W_DUP
    assert cloned.score < clean.score
    # The headline verdict stays a single integer that folds the new signal in.
    assert isinstance(cloned.score, int)
    assert cloned.score == PERFECT_SCORE - cloned.components["duplication"]


@requires_tree_sitter
def test_snapshot_over_deep_nesting_reflects_a_lower_rolled_up_score(
    tmp_path: Path, monkeypatch
) -> None:
    """A real-source snapshot with a deeply-nested function lowers the rolled-up score."""

    def _boom(*_a, **_k):  # pragma: no cover - only fires on a regression
        raise AssertionError("snapshot must not spawn subprocesses")

    monkeypatch.setattr(languages_mod.subprocess, "run", _boom)

    _empty_db(tmp_path)
    deep_src = _deep_nested_source(DEFAULT_RULES.architecture.max_nesting + 3)
    cloned = QualityEvaluator(
        tmp_path,
        rules=DEFAULT_RULES,
        scanned_files=[_scanned(tmp_path, "deep.py", deep_src)],
    ).snapshot()
    assert cloned.metrics.max_nesting > NESTING_FREE
    assert cloned.components["nesting"] > 0
    assert cloned.score < PERFECT_SCORE


@requires_tree_sitter
def test_report_dict_exposes_new_subscores_end_to_end(tmp_path: Path) -> None:
    """``report['health']['components']`` surfaces 'duplication' + 'nesting' (no new field)."""
    _empty_db(tmp_path)
    files = [
        _scanned(tmp_path, "a.py", _CLONE_BODY),
        _scanned(tmp_path, "b.py", _CLONE_BODY),
    ]
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.WARN), scanned_files=files)
    report = ev.evaluate(["a.py", "b.py"], architecture_only=True)

    # Surfaced on the typed report ...
    assert "duplication" in report.health.components
    assert "nesting" in report.health.components
    assert report.health.components["duplication"] >= W_DUP

    # ... and on the ci_checks-compatible report dict (the wire surface).
    d = report.to_report_dict()
    assert "duplication" in d["health"]["components"]
    assert "nesting" in d["health"]["components"]
    assert d["health"]["metrics"]["duplication"] >= 1
    # The rolled-up headline score is the single int from the same fold.
    assert d["health"]["score"] == report.health.score
    assert isinstance(d["health"]["score"], int)


def test_subscores_surface_without_tree_sitter_via_injected_metrics(tmp_path: Path) -> None:
    """Even with no parser, an evaluate() report carries the two new sub-scores at zero.

    Guards that the surfacing is a property of ``compute_health.components`` (always
    present), independent of whether the duplication/nesting passes actually ran.
    """
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "ok.py", "def f():\n    return 1\n")
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.WARN), scanned_files=[sf])
    report = ev.evaluate(["ok.py"], architecture_only=True)
    assert "duplication" in report.health.components
    assert "nesting" in report.health.components
    d = report.to_report_dict()
    assert {"duplication", "nesting"} <= set(d["health"]["components"])


# --------------------------------------------------------------------------- #
# the headline number stays a single int that folds ALL signals
# --------------------------------------------------------------------------- #


def test_headline_score_is_single_int_carrying_all_signals() -> None:
    """``HealthScore.score`` is the one rolled-up int; sub-scores explain it, not replace it."""
    m = QualityMetrics(duplication=1, max_nesting=NESTING_FREE + 1)
    h = QualityEvaluator.compute_health(m, DEFAULT_RULES)
    assert isinstance(h.score, int)
    # The single score equals PERFECT minus the SUM of every component (incl. new ones).
    assert h.score == PERFECT_SCORE - sum(h.components.values())
    # And the two new terms genuinely participate in that sum.
    assert h.components["duplication"] == W_DUP
    assert h.components["nesting"] == W_NESTING


def test_clean_project_rolled_up_score_is_perfect_with_new_terms_present() -> None:
    """A clean project is still a perfect 10000 even with the new terms wired in."""
    h = QualityEvaluator.compute_health(QualityMetrics(), DEFAULT_RULES)
    assert h.score == PERFECT_SCORE == 10000
    assert all(v == 0 for v in h.components.values())


# --------------------------------------------------------------------------- #
# isolation guarantee
# --------------------------------------------------------------------------- #


def test_isolation_does_not_touch_real_home(tmp_path: Path, monkeypatch) -> None:
    """The rolled-up evaluation never reads/writes the real ~/.opencontext."""
    forbidden = Path.home() / ".opencontext"
    real_path_open = Path.open

    def _guarded_open(self: Path, *args, **kwargs):  # pragma: no cover - guard
        assert not str(self).startswith(str(forbidden)), f"touched real home: {self}"
        return real_path_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _guarded_open)
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "ok.py", "def f():\n    return 1\n")
    ev = QualityEvaluator(
        tmp_path, rules=QualityRules(mode=QualityMode.RATCHET), scanned_files=[sf]
    )
    ev.evaluate(["ok.py"], architecture_only=True)


def test_loc_gini_is_report_only_and_does_not_move_score() -> None:
    """The distribution metric is surfaced for explainability but never penalized."""
    clean = QualityEvaluator.compute_health(QualityMetrics(), DEFAULT_RULES)
    skewed = QualityEvaluator.compute_health(QualityMetrics(loc_gini_bp=10000), DEFAULT_RULES)
    assert clean.score == skewed.score == 10000
    assert "loc_gini" not in clean.components and "loc_gini_bp" not in clean.components
    # ...but the raw signal IS carried through for the report/metrics surface.
    assert skewed.metrics.loc_gini_bp == 10000
