"""Regression tests for the quality-engine invariants fixed on this branch.

Each test names the invariant it locks down so a future regression points
straight at the invariant it violated. The invariants are:

1. **Coupling penalty bounded** — every penalty term in ``compute_health`` is
   capped, so a super-coupled node cannot drive the score negative or beyond
   the documented basis-points clamp.
2. **Malformed quality.toml surfaces, never silently defaults** — a
   ``QualityConfigError`` from ``load_rules`` is recorded on the evaluator
   and emitted via ``report.skipped`` so the gate never reports a "clean"
   verdict for a broken config.
3. **ArchitectureAnalyzer caches per-instance** — the dependency graph,
   centrality map, and node->file map are built once per analyzer so a single
   ``analyze()`` does not rebuild the dep graph or re-sweep sqlite, and the
   cycle-finding + boundary-finding passes share a single graph build.
4. **Verify gates skip when there are no changed files** — both
   ``architecture_clean`` and ``quality_standards`` return
   ``SKIPPED reason=no-changed-files`` (with an explanatory message) when
   ``_git_changed_files`` is empty, instead of pretending the gate ran and
   silently approving.
5. **Cycle findings have a stable per-SCC ratchet key** — setting
   ``symbol="cycle:<sorted-members>"`` ensures each distinct cycle hashes to
   a unique SHA-1 in the baseline, so a newly-introduced SCC is not silently
   masked by an unrelated pre-existing one.
6. **God-file LOC threshold is inclusive** (``>=``), matching fan-in.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.models import GateStatus
from opencontext_core.harness.phases import PhaseResult
from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.indexing.scanner import ScannedFile
from opencontext_core.models.project import FileKind
from opencontext_core.quality.architecture import ArchitectureAnalyzer
from opencontext_core.quality.evaluator import (
    _CAP_COUPLING,
    COUPLING_KNEE,
    PERFECT_SCORE,
    W_COUPLING,
    QualityEvaluator,
)
from opencontext_core.quality.models import HealthScore, QualityMetrics
from opencontext_core.quality.rules import DEFAULT_RULES, ArchitectureRules

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _empty_db(root: Path) -> Path:
    db_path = root / ".storage" / "opencontext" / "context_graph.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    db.close()
    return db_path


def _scanned(root: Path, rel: str, content: str) -> ScannedFile:
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


# --------------------------------------------------------------------------- #
# Invariant 1 — coupling penalty bounded (was uncapped)
# --------------------------------------------------------------------------- #


def test_coupling_penalty_is_capped_at_documented_bound() -> None:
    """A super-coupled node cannot exceed ``W_COUPLING * _CAP_COUPLING``.

    The W_COUPLING * (in_degree - COUPLING_KNEE) term used to be uncapped; a
    node with in_degree=10_000 would otherwise contribute 79_920 basis points
    on its own — enough to push the total penalty past PERFECT_SCORE and
    silently turn every other signal into noise. The cap locks it down.
    """
    wild_in = 10_000
    m = QualityMetrics(
        max_in_degree=wild_in,
        # Drive every other term to its cap so they don't mask the coupling
        # term's behavior — the score is already expected to clamp at 0 here.
        cycles=_CAP_COUPLING * 10,  # arbitrary large, beyond the cycles cap
        god_files=99,
        max_cc=99,
        boundary_violations=99,
        max_depth=99,
    )
    h = QualityEvaluator.compute_health(m, DEFAULT_RULES)
    # coupling contributes AT MOST W_COUPLING * _CAP_COUPLING, never more.
    assert h.components["coupling"] == W_COUPLING * _CAP_COUPLING
    # And the whole score is clamped at 0 (every other term is at its cap too).
    assert h.score == 0


def test_coupling_penalty_grows_linearly_below_cap() -> None:
    """Beneath the cap, the penalty keeps the documented ``W_COUPLING * (deg - knee)`` shape."""
    for delta in (1, 5, 12):
        h = QualityEvaluator.compute_health(
            QualityMetrics(max_in_degree=COUPLING_KNEE + delta), DEFAULT_RULES
        )
        assert h.components["coupling"] == W_COUPLING * delta


def test_coupling_penalty_zero_at_or_below_knee() -> None:
    """Soft knee: in_degree <= COUPLING_KNEE costs nothing."""
    for deg in (0, 1, COUPLING_KNEE):
        h = QualityEvaluator.compute_health(QualityMetrics(max_in_degree=deg), DEFAULT_RULES)
        assert h.components["coupling"] == 0


# --------------------------------------------------------------------------- #
# Invariant 2 — malformed quality.toml surfaces via ``skipped``
# --------------------------------------------------------------------------- #


def test_malformed_quality_toml_surfaces_in_skipped(tmp_path: Path) -> None:
    """A ``QualityConfigError`` from ``load_rules`` MUST appear in ``skipped``.

    The previous implementation caught ALL exceptions from ``load_rules`` and
    silently defaulted — a broken config produced a "clean" verdict with no
    signal. The fix records the error on the evaluator and emits it as a
    skipped entry, so consumers (gate / MCP / CI) never see a false clean.
    """
    _empty_db(tmp_path)
    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir(parents=True, exist_ok=True)
    (oc_dir / "quality.toml").write_text(
        "mode = 'not-a-valid-mode'\n",  # QualityMode rejects this
        encoding="utf-8",
    )

    evaluator = QualityEvaluator(tmp_path)
    report = evaluator.evaluate(["ok.py"], architecture_only=True)
    # The error message is present and starts with "quality.toml:" (the
    # documented prefix).
    assert any(s.startswith("quality.toml:") and "mode" in s for s in report.skipped), (
        f"malformed-quality error not surfaced; skipped={report.skipped}"
    )


def test_valid_quality_toml_does_not_add_skipped_entry(tmp_path: Path) -> None:
    """A correct config does not inject any ``quality.toml: ...`` skipped entry."""
    _empty_db(tmp_path)
    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir(parents=True, exist_ok=True)
    (oc_dir / "quality.toml").write_text('mode = "warn"\nmax_fix_loops = 2\n', encoding="utf-8")

    evaluator = QualityEvaluator(tmp_path)
    report = evaluator.evaluate(["ok.py"], architecture_only=True)
    assert not any(s.startswith("quality.toml:") for s in report.skipped)


def test_invalid_toml_surfaces_in_skipped(tmp_path: Path) -> None:
    """Unparseable TOML also surfaces (not just semantic errors)."""
    _empty_db(tmp_path)
    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir(parents=True, exist_ok=True)
    (oc_dir / "quality.toml").write_text("this is = = not toml\n", encoding="utf-8")

    evaluator = QualityEvaluator(tmp_path)
    report = evaluator.evaluate(["ok.py"], architecture_only=True)
    assert any(s.startswith("quality.toml:") for s in report.skipped)


# --------------------------------------------------------------------------- #
# Invariant 3 — ArchitectureAnalyzer caches per-instance
# --------------------------------------------------------------------------- #


def test_dependency_graph_is_built_once_per_analyzer(tmp_path: Path, monkeypatch) -> None:
    """``DependencyGraphBuilder().build`` is invoked exactly once per analyzer.

    Before this fix ``detect_cycles`` and ``detect_boundaries`` each called
    ``.build()`` independently — twice per ``analyze()``. The cache cuts it to
    one. We monkeypatch ``DependencyGraphBuilder`` to count invocations.
    """
    from opencontext_core.indexing import dependency_graph as dg_mod

    real_build = dg_mod.DependencyGraphBuilder.build
    calls = {"count": 0}

    def _track(self, scanned):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return real_build(self, scanned)

    monkeypatch.setattr(dg_mod.DependencyGraphBuilder, "build", _track)

    db_path = _empty_db(tmp_path)
    files = [
        _scanned(tmp_path, "pkg/a.py", "from pkg.b import beta\n"),
        _scanned(tmp_path, "pkg/b.py", "from pkg.a import alpha\n"),
        _scanned(tmp_path, "pkg/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)

    analyzer.analyze(ArchitectureRules())
    analyzer.analyze(ArchitectureRules())

    assert calls["count"] == 1, f"depgraph built {calls['count']} times — cache miss"


def test_centrality_is_computed_once_per_analyzer(tmp_path: Path, monkeypatch) -> None:
    """``compute_centrality`` runs at most once per analyzer, not per-pass."""
    from opencontext_core.indexing.graph_analysis import GraphAnalyzer

    real_compute = GraphAnalyzer.compute_centrality
    calls = {"count": 0}

    def _track(self):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return real_compute(self)

    monkeypatch.setattr(GraphAnalyzer, "compute_centrality", _track)

    db_path = _empty_db(tmp_path)
    files = [
        _scanned(tmp_path, "pkg/a.py", "from pkg.b import beta\n"),
        _scanned(tmp_path, "pkg/b.py", "from pkg.a import alpha\n"),
        _scanned(tmp_path, "pkg/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    # analyze() reaches centrality at least twice in the original code
    # (detect_god_files + _build_metrics). One analyze should yield exactly
    # ONE compute_centrality call now.
    analyzer.analyze(ArchitectureRules())

    assert calls["count"] == 1, f"centrality computed {calls['count']} times — cache miss"


# --------------------------------------------------------------------------- #
# Invariant 4 — verify gates skip on no changed files
# --------------------------------------------------------------------------- #


def test_architecture_gate_skips_with_empty_changed_files(tmp_path: Path, monkeypatch) -> None:
    """``architecture_clean`` SKIPs with reason ``no-changed-files`` on empty scope.

    Before this fix a project without git (or with an empty/clean working tree)
    would still call the evaluator with ``changed_files=[]`` and pass that as
    "no per-file scope" — producing a verbatim whole-graph health without any
    baseline diff and reporting PASSED. Now the gate SKIPs explicitly.
    """
    # Force ``_git_changed_files`` to return ``[]`` (simulates non-git).
    monkeypatch.setattr(HarnessRunner, "_git_changed_files", staticmethod(lambda root: []))

    runner = HarnessRunner(tmp_path)
    state = runner.create_run("sdd", "review")
    state.architecture_baseline = HealthScore(
        score=PERFECT_SCORE, metrics=QualityMetrics(), components={}
    )

    gate = runner._eval_architecture_gate(
        state,
        PhaseResult(phase="verify", status=GateStatus.PASSED),
    )
    assert gate.status == GateStatus.SKIPPED
    assert gate.metadata.get("reason") == "no-changed-files"


def test_quality_standards_gate_skips_with_empty_changed_files(tmp_path: Path, monkeypatch) -> None:
    """``quality_standards`` SKIPs the same way."""
    monkeypatch.setattr(HarnessRunner, "_git_changed_files", staticmethod(lambda root: []))

    runner = HarnessRunner(tmp_path)
    state = runner.create_run("sdd", "review")

    gate = runner._eval_quality_standards_gate(
        state,
        PhaseResult(phase="verify", status=GateStatus.PASSED),
    )
    assert gate.status == GateStatus.SKIPPED
    assert gate.metadata.get("reason") == "no-changed-files"


# --------------------------------------------------------------------------- #
# Invariant 5 — cycle findings have a stable per-SCC ratchet key
# --------------------------------------------------------------------------- #


def test_cycle_finding_has_file_none_and_per_scc_symbol(tmp_path: Path) -> None:
    """The whole-graph cycle finding's ``file`` is None — but ``symbol``

    carries a STABLE per-SCC fingerprint (``"cycle:" + "|".join(members)``)
    so the ratchet key (``finding_key(rule, file, symbol)``) is unique per
    distinct cycle across the repo. Without this, every cycle in the repo
    would hash to one key (``sha1("max_cycles||")``) and a newly-introduced
    SCC would silently masquerade as a previously-saved baseline cycle.
    """
    db_path = _empty_db(tmp_path)
    files1 = [
        _scanned(tmp_path, "pkg/a.py", "from pkg.b import beta\n"),
        _scanned(tmp_path, "pkg/b.py", "from pkg.a import alpha\n"),
        _scanned(tmp_path, "pkg/__init__.py", ""),
    ]
    report1 = ArchitectureAnalyzer(db_path, scanned_files=files1).analyze(ArchitectureRules())
    cycle_findings_1 = [f for f in report1.findings if f.rule == "max_cycles"]
    assert cycle_findings_1, "expected at least one cycle finding"
    for f in cycle_findings_1:
        assert f.file is None
        assert f.symbol is not None and f.symbol.startswith("cycle:")
        assert "pkg/a.py" in f.symbol and "pkg/b.py" in f.symbol
        assert "members" in f.metadata
        assert set(f.metadata["members"]) == {"pkg/a.py", "pkg/b.py"}

    # Two structurally distinct cycles must produce two DISTINCT ratchet keys.
    files2 = [
        *files1,
        _scanned(tmp_path, "pkg/c.py", "from pkg.d import delta\n"),
        _scanned(tmp_path, "pkg/d.py", "from pkg.c import gamma\n"),
    ]
    report2 = ArchitectureAnalyzer(db_path, scanned_files=files2).analyze(ArchitectureRules())
    cycle_findings_2 = [f for f in report2.findings if f.rule == "max_cycles"]
    assert len(cycle_findings_2) == 2  # both SCCs flagged
    symbols = {f.symbol for f in cycle_findings_2}
    assert len(symbols) == 2, (
        f"each SCC must have a distinct ratchet-key fingerprint; collapsed to {symbols}"
    )


# --------------------------------------------------------------------------- #
# Invariant 6 — God-file LOC threshold is inclusive (``>=``)
# --------------------------------------------------------------------------- #


def test_god_file_loc_threshold_is_inclusive(tmp_path: Path) -> None:
    """A file exactly at ``god_file_loc`` is flagged (>= not >)."""
    db_path = _empty_db(tmp_path)
    # Build a file with exactly the threshold line count.
    BODY_LINES = 40  # == threshold below
    content = "\n".join(f"x{i} = {i}" for i in range(BODY_LINES - 1)) + "\n"
    # The analyzer's LOC = newlines + 1 (when content is non-empty). With
    # BODY_LINES-1 lines, content.count("\n") = BODY_LINES-1 -> loc == BODY_LINES.
    files = [_scanned(tmp_path, "src/exact.py", content)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)

    god_files = analyzer.detect_god_files(
        ArchitectureRules(god_file_in_degree=999, god_file_loc=BODY_LINES)
    )
    paths = {g.file for g in god_files}
    assert "src/exact.py" in paths, (
        f"file at exact LOC cap should be flagged (inclusive); got gods={paths}"
    )
