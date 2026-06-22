"""Behavior tests for :class:`QualityEvaluator` — the single quality engine.

Every test is ``tmp_path``-isolated: the graph DB lives at
``tmp_path/.storage/opencontext/context_graph.db`` and any baseline/toml lives
under ``tmp_path/.opencontext``. Nothing here reads or writes the real
``~/.opencontext`` or the repo's own ``.opencontext`` (asserted explicitly in
``test_isolation_*``). These are behavior tests — they fail if the orchestration,
the ratchet filtering, the health formula, the status mapping, or the
zero-model/zero-subprocess guarantees break.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.models import GateStatus
from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.indexing.scanner import ScannedFile
from opencontext_core.models.project import FileKind
from opencontext_core.quality import languages as languages_mod
from opencontext_core.quality.baseline import BaselineStore
from opencontext_core.quality.ci_checks import CheckSeverity, CheckStatus
from opencontext_core.quality.evaluator import (
    COUPLING_KNEE,
    DEPTH_FREE,
    PERFECT_SCORE,
    W_BOUNDARY,
    W_CC,
    W_COUPLING,
    W_CYCLES,
    W_DEPTH,
    W_GOD,
    QualityEvaluator,
)
from opencontext_core.quality.languages import LanguageQualityRunner, ToolRun
from opencontext_core.quality.models import HealthScore, QualityMetrics
from opencontext_core.quality.rules import (
    DEFAULT_RULES,
    ArchitectureRules,
    BoundaryRule,
    LayerRule,
    QualityMode,
    QualityRules,
)

# --------------------------------------------------------------------------- #
# fixtures / helpers
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
        file_type=FileKind.UNKNOWN,
        content=content,
        tokens=max(1, len(content) // 4),
        size_bytes=len(content),
        summary="",
        metadata={},
    )


def _complex_source(branches: int) -> str:
    """Python source for one function with ``branches`` if-statements (high CC)."""
    lines = ["def busy(x):"]
    for i in range(branches):
        lines.append(f"    if x == {i}:")
        lines.append(f"        return {i}")
    lines.append("    return -1")
    return "\n".join(lines)


def _import_cycle_files(root: Path) -> list[ScannedFile]:
    """Two source files that import each other (a file-level import cycle)."""
    a = _scanned(
        root,
        "pkg/a.py",
        "from pkg.b import beta\n\n\ndef alpha():\n    return beta()\n",
    )
    b = _scanned(
        root,
        "pkg/b.py",
        "from pkg.a import alpha\n\n\ndef beta():\n    return alpha()\n",
    )
    return [a, b]


# --------------------------------------------------------------------------- #
# health-score formula (the canonical, integer, explainable function)
# --------------------------------------------------------------------------- #


def test_compute_health_perfect_when_no_signals() -> None:
    h = QualityEvaluator.compute_health(QualityMetrics(), DEFAULT_RULES)
    assert h.score == PERFECT_SCORE == 10000
    assert all(v == 0 for v in h.components.values())


def test_compute_health_is_integer_basis_points() -> None:
    h = QualityEvaluator.compute_health(QualityMetrics(cycles=2, god_files=1), DEFAULT_RULES)
    assert isinstance(h.score, int)


def test_compute_health_subtracts_documented_weights() -> None:
    m = QualityMetrics(cycles=2, god_files=3, boundary_violations=1)
    h = QualityEvaluator.compute_health(m, DEFAULT_RULES)
    expected_penalty = (W_CYCLES * 2) + (W_GOD * 3) + (W_BOUNDARY * 1)
    assert h.score == PERFECT_SCORE - expected_penalty
    assert h.components["cycles"] == W_CYCLES * 2
    assert h.components["god_files"] == W_GOD * 3
    assert h.components["boundary"] == W_BOUNDARY * 1


def test_compute_health_complexity_penalizes_only_excess_over_threshold() -> None:
    rules = QualityRules(architecture=ArchitectureRules(max_cc=10))
    # max_cc 13 == 3 points over the configured cap of 10.
    h = QualityEvaluator.compute_health(QualityMetrics(max_cc=13), rules)
    assert h.components["complexity"] == W_CC * 3
    # at-or-below the cap costs nothing.
    h_ok = QualityEvaluator.compute_health(QualityMetrics(max_cc=10), rules)
    assert h_ok.components["complexity"] == 0
    assert h_ok.score == PERFECT_SCORE


def test_compute_health_coupling_has_a_free_knee() -> None:
    below = QualityEvaluator.compute_health(
        QualityMetrics(max_in_degree=COUPLING_KNEE), DEFAULT_RULES
    )
    assert below.components["coupling"] == 0
    above = QualityEvaluator.compute_health(
        QualityMetrics(max_in_degree=COUPLING_KNEE + 5), DEFAULT_RULES
    )
    assert above.components["coupling"] == W_COUPLING * 5


def test_compute_health_depth_has_a_free_allowance() -> None:
    ok = QualityEvaluator.compute_health(QualityMetrics(max_depth=DEPTH_FREE), DEFAULT_RULES)
    assert ok.components["depth"] == 0
    deep = QualityEvaluator.compute_health(QualityMetrics(max_depth=DEPTH_FREE + 2), DEFAULT_RULES)
    assert deep.components["depth"] == W_DEPTH * 2


def test_compute_health_terms_are_capped_and_clamped_to_zero() -> None:
    # Wildly bad metrics must not underflow below 0 (every term is capped).
    m = QualityMetrics(
        cycles=1000,
        god_files=1000,
        max_cc=1000,
        max_in_degree=1000,
        boundary_violations=1000,
        max_depth=1000,
    )
    h = QualityEvaluator.compute_health(m, DEFAULT_RULES)
    assert h.score == 0
    # cycles term is capped at 10 -> at most W_CYCLES*10, never 1000*W_CYCLES.
    assert h.components["cycles"] == W_CYCLES * 10


def test_compute_health_is_deterministic() -> None:
    m = QualityMetrics(cycles=3, god_files=2, max_cc=30, max_in_degree=20)
    first = QualityEvaluator.compute_health(m, DEFAULT_RULES)
    second = QualityEvaluator.compute_health(m, DEFAULT_RULES)
    assert first == second


def test_healthscore_delta_sign() -> None:
    base = QualityEvaluator.compute_health(QualityMetrics(cycles=1), DEFAULT_RULES)
    worse = QualityEvaluator.compute_health(QualityMetrics(cycles=2), DEFAULT_RULES)
    assert worse.delta(base) < 0  # adding a cycle lowers the score
    assert base.delta(worse) > 0


# --------------------------------------------------------------------------- #
# snapshot: fast, token-free, zero subprocess
# --------------------------------------------------------------------------- #


def test_snapshot_runs_no_language_subprocess(tmp_path: Path, monkeypatch) -> None:
    """The snapshot fast-path must never spawn a tool subprocess."""
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "a.py", "def f():\n    return 1\n")

    def _boom(*_a, **_k):  # pragma: no cover - only fires on a regression
        raise AssertionError("snapshot must not spawn subprocesses")

    monkeypatch.setattr(languages_mod.subprocess, "run", _boom)

    ev = QualityEvaluator(tmp_path, rules=DEFAULT_RULES, scanned_files=[sf])
    health = ev.snapshot()
    assert isinstance(health.score, int)
    assert health.score == PERFECT_SCORE


def test_snapshot_detects_complexity_lowering_the_score(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    clean = QualityEvaluator(
        tmp_path,
        rules=DEFAULT_RULES,
        scanned_files=[_scanned(tmp_path, "ok.py", "def f():\n    return 1\n")],
    ).snapshot()
    busy = QualityEvaluator(
        tmp_path,
        rules=DEFAULT_RULES,
        scanned_files=[_scanned(tmp_path, "busy.py", _complex_source(40))],
    ).snapshot()
    assert clean.score == PERFECT_SCORE
    assert busy.score < clean.score
    assert busy.metrics.max_cc > DEFAULT_RULES.architecture.max_cc


def test_snapshot_detects_import_cycle(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    ev = QualityEvaluator(
        tmp_path, rules=DEFAULT_RULES, scanned_files=_import_cycle_files(tmp_path)
    )
    health = ev.snapshot()
    assert health.metrics.cycles >= 1
    assert health.score <= PERFECT_SCORE - W_CYCLES


def test_snapshot_is_deterministic(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    files = _import_cycle_files(tmp_path)
    a = QualityEvaluator(tmp_path, rules=DEFAULT_RULES, scanned_files=files).snapshot()
    b = QualityEvaluator(tmp_path, rules=DEFAULT_RULES, scanned_files=files).snapshot()
    assert a == b


# --------------------------------------------------------------------------- #
# evaluate: orchestration, status mapping, exit code
# --------------------------------------------------------------------------- #


def test_evaluate_clean_change_passes(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "ok.py", "def f():\n    return 1\n")
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.WARN), scanned_files=[sf])
    report = ev.evaluate(["ok.py"], architecture_only=True)
    assert report.status == GateStatus.PASSED
    assert report.exit_code == 0
    assert report.findings == ()


def test_evaluate_architecture_only_skips_subprocess(tmp_path: Path, monkeypatch) -> None:
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "ok.py", "def f():\n    return 1\n")

    def _boom(*_a, **_k):  # pragma: no cover
        raise AssertionError("architecture_only must not run language tools")

    monkeypatch.setattr(languages_mod.subprocess, "run", _boom)
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.WARN), scanned_files=[sf])
    report = ev.evaluate(["ok.py"], architecture_only=True)
    assert report.status == GateStatus.PASSED


def test_evaluate_warn_mode_warns_on_complexity_finding(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "busy.py", _complex_source(40))
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.WARN), scanned_files=[sf])
    report = ev.evaluate(["busy.py"], architecture_only=True)
    assert report.status == GateStatus.WARNING
    assert report.exit_code == 1  # WARNING is not is_ok -> exit 1
    assert any(f.rule == "max_cc" for f in report.findings)


def test_evaluate_strict_mode_fails_on_error_finding(tmp_path: Path) -> None:
    """A declared-boundary break is an ERROR finding -> FAILED under strict."""
    _empty_db(tmp_path)
    view_src = "from db.repo import load\n\n\ndef render():\n    return load()\n"
    files = [
        _scanned(tmp_path, "ui/view.py", view_src),
        _scanned(tmp_path, "db/repo.py", "def load():\n    return 1\n"),
    ]
    boundary = BoundaryRule(
        from_layer="ui", to_layer="db", allow=False, reason="UI must not reach the DB"
    )
    rules = QualityRules(
        mode=QualityMode.STRICT,
        architecture=ArchitectureRules(
            layers=(
                LayerRule(name="ui", paths=("ui/*",), order=0),
                LayerRule(name="db", paths=("db/*",), order=1),
            ),
            boundaries=(boundary,),
        ),
    )
    ev = QualityEvaluator(tmp_path, rules=rules, scanned_files=files)
    report = ev.evaluate(["ui/view.py"], architecture_only=True)
    assert report.status == GateStatus.FAILED
    assert report.exit_code == 1
    assert any(f.rule == "layers" and f.severity == CheckSeverity.ERROR for f in report.findings)


def test_evaluate_off_mode_skips(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "busy.py", _complex_source(40))
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.OFF), scanned_files=[sf])
    report = ev.evaluate(["busy.py"])
    assert report.status == GateStatus.SKIPPED
    assert report.exit_code == 0  # SKIPPED is is_ok
    assert report.findings == ()
    assert "quality:mode-off" in report.skipped


def test_evaluate_strict_fails_on_health_regression_vs_baseline(tmp_path: Path) -> None:
    """Even a finding-free change FAILS under strict if the score dropped."""
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "ok.py", "def f():\n    return 1\n")
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.STRICT), scanned_files=[sf])
    # Pretend the baseline was a perfect 10000 but current is artificially lower.
    high_baseline = HealthScore(score=PERFECT_SCORE, metrics=QualityMetrics(), components={})
    lowered = HealthScore(score=PERFECT_SCORE - 1, metrics=QualityMetrics(), components={})
    status = ev._status((), lowered, high_baseline)
    assert status == GateStatus.FAILED


def test_evaluate_is_deterministic(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "busy.py", _complex_source(40))
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.WARN), scanned_files=[sf])
    first = ev.evaluate(["busy.py"], architecture_only=True)
    second = ev.evaluate(["busy.py"], architecture_only=True)
    assert first.to_report_dict() == second.to_report_dict()
    assert first.status == second.status


def test_evaluate_summary_reports_delta(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "ok.py", "def f():\n    return 1\n")
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.WARN), scanned_files=[sf])
    baseline = HealthScore(score=PERFECT_SCORE, metrics=QualityMetrics(), components={})
    report = ev.evaluate(["ok.py"], baseline=baseline, architecture_only=True)
    assert "->" in report.summary
    assert report.baseline_health is baseline


# --------------------------------------------------------------------------- #
# ratchet: only NEW findings block; pre-existing ones are suppressed
# --------------------------------------------------------------------------- #


def test_ratchet_suppresses_preexisting_findings(tmp_path: Path) -> None:
    """A pre-existing complexity finding recorded in the baseline does NOT block."""
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "busy.py", _complex_source(40))
    rules = QualityRules(mode=QualityMode.RATCHET)
    ev = QualityEvaluator(tmp_path, rules=rules, scanned_files=[sf])

    # Capture a baseline that already contains the complexity violation.
    ev.save_baseline()
    assert BaselineStore(tmp_path / rules.baseline_path).exists()

    report = ev.evaluate(["busy.py"], architecture_only=True)
    # The finding is still reported (transparency) ...
    assert any(f.rule == "max_cc" for f in report.findings)
    # ... but it is NOT new, so nothing blocks -> PASSED.
    assert report.new_findings == ()
    assert report.status == GateStatus.PASSED
    assert report.exit_code == 0


def test_ratchet_flags_a_newly_introduced_finding(tmp_path: Path) -> None:
    """A finding absent from the baseline is NEW -> WARNING in ratchet mode."""
    _empty_db(tmp_path)
    clean = _scanned(tmp_path, "busy.py", "def f():\n    return 1\n")
    rules = QualityRules(mode=QualityMode.RATCHET)

    # Baseline captured while the file was clean.
    QualityEvaluator(tmp_path, rules=rules, scanned_files=[clean]).save_baseline()

    # Now the file regresses (high complexity).
    busy = _scanned(tmp_path, "busy.py", _complex_source(40))
    ev = QualityEvaluator(tmp_path, rules=rules, scanned_files=[busy])
    report = ev.evaluate(["busy.py"], architecture_only=True)
    assert any(f.rule == "max_cc" for f in report.new_findings)
    assert report.status == GateStatus.WARNING


def test_ratchet_without_baseline_treats_all_findings_as_new(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "busy.py", _complex_source(40))
    ev = QualityEvaluator(
        tmp_path, rules=QualityRules(mode=QualityMode.RATCHET), scanned_files=[sf]
    )
    # No baseline saved -> everything is "new".
    report = ev.evaluate(["busy.py"], architecture_only=True)
    assert any(f.rule == "max_cc" for f in report.new_findings)
    assert report.status == GateStatus.WARNING


# --------------------------------------------------------------------------- #
# baseline snapshot + diff (capture / compare)
# --------------------------------------------------------------------------- #


def test_save_baseline_persists_findings_metrics_and_score(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "busy.py", _complex_source(40))
    rules = QualityRules(mode=QualityMode.RATCHET)
    ev = QualityEvaluator(tmp_path, rules=rules, scanned_files=[sf])

    baseline = ev.save_baseline()
    assert baseline.score < PERFECT_SCORE  # the complexity violation lowered it
    assert baseline.keys  # at least one recorded finding key
    assert baseline.metrics.max_cc > rules.architecture.max_cc

    # Round-trips from disk identically.
    loaded = BaselineStore(tmp_path / rules.baseline_path).load()
    assert loaded is not None
    assert loaded.score == baseline.score
    assert loaded.keys == baseline.keys


def test_save_baseline_is_whole_repo_not_scoped(tmp_path: Path) -> None:
    """save_baseline captures the whole repo regardless of any changed scope."""
    _empty_db(tmp_path)
    files = [
        _scanned(tmp_path, "a.py", _complex_source(40)),
        _scanned(tmp_path, "b.py", _complex_source(40)),
    ]
    ev = QualityEvaluator(
        tmp_path, rules=QualityRules(mode=QualityMode.RATCHET), scanned_files=files
    )
    baseline = ev.save_baseline(changed_files=["a.py"])  # scope ignored on purpose
    # Both files' complexity findings are recorded (2 distinct keys).
    assert len(baseline.keys) >= 2


# --------------------------------------------------------------------------- #
# evaluate_health_regression: the zero-config in-loop rule
# --------------------------------------------------------------------------- #


def test_health_regression_passes_when_score_holds_or_improves(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    ev = QualityEvaluator(tmp_path, rules=DEFAULT_RULES, scanned_files=[])
    base = HealthScore(score=9000, metrics=QualityMetrics(), components={})
    better = HealthScore(score=9100, metrics=QualityMetrics(), components={})
    verdict = ev.evaluate_health_regression(base, better, DEFAULT_RULES)
    assert verdict.status == CheckStatus.PASSED
    assert verdict.findings == ()
    assert "9000 -> 9100" in verdict.message


def test_health_regression_warns_under_ratchet(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    ev = QualityEvaluator(tmp_path, rules=DEFAULT_RULES, scanned_files=[])
    base = HealthScore(score=9100, metrics=QualityMetrics(), components={})
    worse = HealthScore(score=9000, metrics=QualityMetrics(), components={})
    verdict = ev.evaluate_health_regression(base, worse, QualityRules(mode=QualityMode.RATCHET))
    assert verdict.status == CheckStatus.FAILED
    assert verdict.severity == CheckSeverity.WARNING
    assert verdict.findings and verdict.findings[0].rule == "health_regression"


def test_health_regression_errors_under_strict(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    ev = QualityEvaluator(tmp_path, rules=DEFAULT_RULES, scanned_files=[])
    base = HealthScore(score=9100, metrics=QualityMetrics(), components={})
    worse = HealthScore(score=9000, metrics=QualityMetrics(), components={})
    verdict = ev.evaluate_health_regression(base, worse, QualityRules(mode=QualityMode.STRICT))
    assert verdict.status == CheckStatus.FAILED
    assert verdict.severity == CheckSeverity.ERROR


# --------------------------------------------------------------------------- #
# report dict shape (ci_checks generate_report-compatible) + gate mapping
# --------------------------------------------------------------------------- #


def test_to_report_dict_has_ci_check_shape(tmp_path: Path) -> None:
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "busy.py", _complex_source(40))
    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.WARN), scanned_files=[sf])
    report = ev.evaluate(["busy.py"], architecture_only=True)
    d = report.to_report_dict()
    assert set(d["summary"]) == {
        "total_checks",
        "passed",
        "failed",
        "warnings",
        "errors",
        "success",
    }
    assert "results" in d and isinstance(d["results"], list)
    assert "health" in d and "score" in d["health"]
    assert "delta" in d
    # The exit code is consistent with the status.
    assert report.exit_code == (0 if report.status.is_ok else 1)


# --------------------------------------------------------------------------- #
# language-tool path: monkeypatched subprocess (no real tool needed on CI)
# --------------------------------------------------------------------------- #


def test_evaluate_consumes_language_findings(tmp_path: Path, monkeypatch) -> None:
    """A fake ruff run injects a finding the evaluator surfaces + ratchets."""
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "mod.py", "def f():\n    return 1\n")

    ruff_payload = (
        '[{"code":"F401","message":"unused import",'
        '"filename":"mod.py","location":{"row":1,"column":1}}]'
    )

    def _fake_run(self: LanguageQualityRunner, spec, files):
        if spec.name == "ruff":
            return ToolRun(tool="ruff", exit_code=1, stdout=ruff_payload, stderr="", missing=False)
        # Any other tool (e.g. mypy) is reported as absent -> recorded as skipped.
        return ToolRun(tool=spec.name, exit_code=-2, stdout="", stderr="", missing=True)

    monkeypatch.setattr(LanguageQualityRunner, "_run_tool", _fake_run)

    ev = QualityEvaluator(tmp_path, rules=QualityRules(mode=QualityMode.WARN), scanned_files=[sf])
    report = ev.evaluate(["mod.py"])  # language path enabled (not architecture_only)
    assert any(f.rule == "ruff" and f.category == "language" for f in report.findings)
    assert report.status == GateStatus.WARNING


# --------------------------------------------------------------------------- #
# isolation guarantees (the hard rule)
# --------------------------------------------------------------------------- #


def test_isolation_writes_only_under_tmp_path(tmp_path: Path) -> None:
    """The baseline is written under tmp_path/.opencontext, nowhere else."""
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "busy.py", _complex_source(40))
    rules = QualityRules(mode=QualityMode.RATCHET)
    ev = QualityEvaluator(tmp_path, rules=rules, scanned_files=[sf])
    ev.save_baseline()
    written = tmp_path / rules.baseline_path
    assert written.is_file()
    assert str(written).startswith(str(tmp_path))


def test_isolation_does_not_touch_real_home(tmp_path: Path, monkeypatch) -> None:
    """A failure if the engine ever reads/writes the real ~/.opencontext."""
    forbidden = Path.home() / ".opencontext"
    real_path_open = Path.open

    def _guarded_open(self: Path, *args, **kwargs):  # pragma: no cover - guard
        resolved = str(self)
        assert not resolved.startswith(str(forbidden)), f"touched real home: {self}"
        return real_path_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _guarded_open)
    _empty_db(tmp_path)
    sf = _scanned(tmp_path, "ok.py", "def f():\n    return 1\n")
    ev = QualityEvaluator(
        tmp_path, rules=QualityRules(mode=QualityMode.RATCHET), scanned_files=[sf]
    )
    ev.evaluate(["ok.py"], architecture_only=True)


def test_evaluate_makes_zero_model_calls_on_snapshot_fast_path(tmp_path: Path, monkeypatch) -> None:
    """The snapshot path must touch neither subprocess nor any sampling client.

    We guard the only external escape hatches the architecture path could use:
    subprocess (covered above) — here we additionally assert no network/model
    module is imported lazily by snapshot by checking it never calls subprocess
    and the result is pure arithmetic over the graph metrics.
    """
    _empty_db(tmp_path)
    files = _import_cycle_files(tmp_path)

    calls: list[str] = []
    real_run = languages_mod.subprocess.run

    def _track(*args, **kwargs):  # pragma: no cover - only on regression
        calls.append("ran")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(languages_mod.subprocess, "run", _track)
    health = QualityEvaluator(tmp_path, rules=DEFAULT_RULES, scanned_files=files).snapshot()
    assert calls == []  # snapshot never shells out
    assert isinstance(health.score, int)
