"""Tests for the architecture/quality registration shim in ``quality.ci_checks``.

The shim (:func:`architecture_check_results`) lets ``opencontext ci-check run``
surface the architecture + code-quality evaluation through the SAME report
schema the markdown pattern checks already use — one rules source, two entry
points (the CI check and the harness gate). These tests assert:

* the shim folds straight into :meth:`CheckRunner.generate_report` (one schema);
* findings map 1:1 to :class:`CheckResult` rows via the canonical
  ``models.to_check_result`` helper (no re-implementation, no drift);
* the existing ``CheckSeverity``/``CheckStatus``/``CheckResult``/
  ``CheckDefinition``/``CheckRunner`` shapes are untouched (the whole quality
  package depends on them);
* the path is deterministic and makes ZERO model calls;
* importing ``ci_checks`` does not eagerly import the evaluator (no import
  cycle: ``quality.evaluator``/``quality.models`` import this module at load).

Isolation: every test uses ``tmp_path`` as the project root. The evaluator only
ever derives paths from that root (DB under ``tmp_path/.storage/opencontext``,
baseline under ``tmp_path/.opencontext``, config at
``tmp_path/.opencontext/quality.toml``), so the real ``~/.opencontext`` and the
repository's own ``.opencontext`` are never read or written. ``HOME`` is
redirected to a tmp sentinel and asserted to stay empty.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from opencontext_core.quality.ci_checks import (
    ARCHITECTURE_CHECK_NAME,
    CheckDefinition,
    CheckResult,
    CheckRunner,
    CheckSeverity,
    CheckStatus,
    architecture_check_results,
)
from opencontext_core.quality.models import to_check_result
from opencontext_core.quality.rules import (
    QualityMode,
    QualityRules,
)

# Repo-level paths used ONLY to assert the shim never touches them.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPO_OC = _REPO_ROOT / ".opencontext"


# --------------------------------------------------------------------------- #
# Fixtures / helpers (all tmp_path-isolated)
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _real_dirs_untouched(monkeypatch: pytest.MonkeyPatch, tmp_path_factory):
    """Assert the run touches neither ``~/.opencontext`` nor the repo ``.opencontext``.

    The shim must derive every path from the project root it is handed. We snapshot
    the two OpenContext config dirs around every test and assert they are
    byte-for-byte unchanged: a stray read is harmless; a stray write fails loudly.

    Parallel-safety (``-n auto``): both the real ``~/.opencontext`` and the repo
    ``.opencontext`` are process-shared, so a *concurrent* worker writing there
    would flip this invariant and falsely blame this test. To keep the check
    hermetic we redirect HOME (and the XDG dirs) to a private, per-test sentinel
    before snapshotting — ``~/.opencontext`` then resolves to an empty dir no other
    worker shares, while the shim's own writes under HOME are still caught. Tool
    discovery is unaffected (console scripts resolve via PATH/the active venv, not
    HOME), and the sibling ``_deterministic_language_layer`` fixture stubs out the
    subprocess language layer, so no user-site shim is exercised.
    """
    sentinel_home = tmp_path_factory.mktemp("home_sentinel")
    monkeypatch.setenv("HOME", str(sentinel_home))
    monkeypatch.setenv("USERPROFILE", str(sentinel_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(sentinel_home / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(sentinel_home / ".local" / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(sentinel_home / ".cache"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: sentinel_home))

    home_oc = Path.home() / ".opencontext"
    before_home = _snapshot_with_text(home_oc)
    before_repo = _snapshot_with_text(_REPO_OC)
    yield
    assert _snapshot_with_text(home_oc) == before_home, "run mutated ~/.opencontext"
    assert _snapshot_with_text(_REPO_OC) == before_repo, "run mutated repo .opencontext"


@pytest.fixture(autouse=True)
def _deterministic_language_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the (environment-dependent) language subprocess layer.

    The architecture/quality evaluation includes a language step that shells out
    to real tools (ruff/mypy/...). Their presence + behaviour vary by machine
    and are exercised in ``test_languages.py``; here we want the DETERMINISTIC
    architecture path that the shim folds in. We stub ``LanguageQualityRunner``
    so it contributes no findings, leaving the graph/parser-driven architecture
    findings (which are deterministic) as the signal under test.

    Tests that specifically want the real language path opt out by re-patching.
    """
    import opencontext_core.quality.languages as lang_mod

    def _no_language_findings(self, *a: object, **k: object):
        return ((), ())

    monkeypatch.setattr(lang_mod.LanguageQualityRunner, "run", _no_language_findings)


def _write_project(root: Path, files: dict[str, str]) -> None:
    """Write ``{relpath: content}`` under ``root`` (creating parents)."""
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _clean_project(root: Path) -> None:
    """A trivially clean project: one small, low-complexity module."""
    _write_project(root, {"src/a.py": "def add(x: int, y: int) -> int:\n    return x + y\n"})


def _high_complexity_source() -> str:
    """A single function with many branches (deterministic CC well above 1)."""
    body = ["def classify(x: int) -> int:"]
    for i in range(8):
        body.append(f"    if x == {i}:")
        body.append(f"        return {i}")
    body.append("    return -1")
    return "\n".join(body) + "\n"


def _rules_with_baseline_isolated(root: Path, **kw: object) -> QualityRules:
    """Build ``QualityRules`` whose baseline path stays under ``root``.

    ``baseline_path`` is relative, and the evaluator joins it onto the project
    root, so this is already isolated; we pin it explicitly for clarity.
    """
    kw.setdefault("baseline_path", ".opencontext/quality-baseline.json")
    return QualityRules(**kw)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Existing public surface is untouched (the package depends on these shapes)
# --------------------------------------------------------------------------- #


class TestExistingSurfaceUnchanged:
    def test_check_result_field_shape(self) -> None:
        """``CheckResult`` keeps its exact field set — the shim relies on it."""
        cr = CheckResult(
            check_name="x",
            status=CheckStatus.FAILED,
            severity=CheckSeverity.ERROR,
            message="m",
        )
        assert cr.check_name == "x"
        assert cr.status == CheckStatus.FAILED
        assert cr.severity == CheckSeverity.ERROR
        # Optional row fields remain present + default to None.
        assert cr.file is None and cr.line is None and cr.suggestion is None
        assert cr.diff is None

    def test_severity_and_status_members(self) -> None:
        assert {s.value for s in CheckSeverity} == {"info", "warning", "error", "critical"}
        assert {s.value for s in CheckStatus} == {"passed", "failed", "skipped", "error"}

    def test_check_definition_still_parses(self) -> None:
        """The markdown ``CheckDefinition`` path is unaffected by the shim."""
        check = CheckDefinition(
            name="N",
            description="d",
            severity=CheckSeverity.WARNING,
            files=["*.py"],
            patterns=["TODO"],
        )
        assert "name: N" in check.to_markdown()

    def test_runner_pattern_path_intact(self, tmp_path: Path) -> None:
        """The legacy pattern check still works (no regression from the shim)."""
        (tmp_path / "f.py").write_text("# TODO: later\n", encoding="utf-8")
        runner = CheckRunner(tmp_path)
        check = CheckDefinition(
            name="TODO",
            description="d",
            severity=CheckSeverity.WARNING,
            files=["*.py"],
            patterns=["TODO"],
        )
        results = runner.run_check(check, ["f.py"])
        assert results[0].status == CheckStatus.FAILED


# --------------------------------------------------------------------------- #
# No import cycle: ci_checks must not eagerly import the evaluator
# --------------------------------------------------------------------------- #


class TestNoImportCycle:
    def test_importing_ci_checks_does_not_pull_evaluator(self) -> None:
        """``ci_checks`` import alone must not load ``quality.evaluator``.

        ``quality.evaluator`` and ``quality.models`` import ``ci_checks`` at
        module load; a top-level import of the evaluator here would form a
        cycle. Reload ``ci_checks`` with the evaluator absent and confirm it
        does not get imported as a side effect.

        Critically, this RESTORES the original ``sys.modules`` entries afterward
        so it cannot leak a duplicate ``ci_checks`` (and thus a second
        ``CheckSeverity`` class) into the rest of the session — a fresh import
        left in ``sys.modules`` would make later ``is``/identity checks against
        this file's top-level imports fail spuriously.
        """
        targets = ("opencontext_core.quality.ci_checks", "opencontext_core.quality.evaluator")
        saved = {name: sys.modules.get(name) for name in targets}
        try:
            for name in targets:
                sys.modules.pop(name, None)
            ci = importlib.import_module("opencontext_core.quality.ci_checks")
            assert hasattr(ci, "architecture_check_results")
            assert "opencontext_core.quality.evaluator" not in sys.modules
        finally:
            # Restore the originally-cached modules so no duplicate class leaks.
            for name, mod in saved.items():
                if mod is not None:
                    sys.modules[name] = mod
                else:
                    sys.modules.pop(name, None)


# --------------------------------------------------------------------------- #
# architecture_check_results: clean scope
# --------------------------------------------------------------------------- #


class TestArchitectureCheckResultsClean:
    def test_clean_change_yields_single_passed_row(self, tmp_path: Path) -> None:
        _clean_project(tmp_path)
        rows = architecture_check_results(tmp_path, ["src/a.py"])
        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row, CheckResult)
        assert row.status == CheckStatus.PASSED
        assert row.severity == CheckSeverity.INFO
        assert row.check_name == ARCHITECTURE_CHECK_NAME

    def test_whole_repo_scope_when_changed_files_none(self, tmp_path: Path) -> None:
        """``changed_files=None`` scopes to the whole project (still clean)."""
        _clean_project(tmp_path)
        rows = architecture_check_results(tmp_path, None)
        assert rows and all(isinstance(r, CheckResult) for r in rows)
        assert rows[0].status == CheckStatus.PASSED

    def test_accepts_str_root(self, tmp_path: Path) -> None:
        """``root`` may be a ``str`` (the CLI passes a positional path string)."""
        _clean_project(tmp_path)
        rows = architecture_check_results(str(tmp_path), ["src/a.py"])
        assert rows[0].status == CheckStatus.PASSED


# --------------------------------------------------------------------------- #
# architecture_check_results: findings map to CheckResult rows
# --------------------------------------------------------------------------- #


class TestArchitectureCheckResultsFindings:
    def test_complexity_finding_maps_to_failed_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real architecture finding (high CC) folds into a FAILED row.

        We force the finding deterministically by lowering ``max_cc`` to 1 via a
        ``quality.toml`` under the (tmp) project, then assert the shim emits a
        ``CheckResult`` whose ``check_name`` is the finding's RULE (``max_cc``),
        status FAILED, file/line carried through — i.e. the canonical
        ``to_check_result`` mapping, not a re-implementation.

        tree-sitter availability is environment-dependent; if the parser is
        unavailable the complexity pass degrades honestly (skipped, no finding),
        so we skip rather than assert a false negative.
        """
        from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser

        if not TreeSitterParser().is_available():
            pytest.skip("tree-sitter unavailable; complexity pass degrades to skipped")

        _write_project(
            tmp_path,
            {
                "src/complex.py": _high_complexity_source(),
                # warn mode + max_cc=1 so the single high-CC function is a finding.
                ".opencontext/quality.toml": 'mode = "warn"\n\n[architecture]\nmax_cc = 1\n',
            },
        )

        rows = architecture_check_results(tmp_path, ["src/complex.py"])

        cc_rows = [r for r in rows if r.check_name == "max_cc"]
        assert cc_rows, f"expected a max_cc row, got {[r.check_name for r in rows]}"
        row = cc_rows[0]
        assert row.status == CheckStatus.FAILED  # a Finding is always a violation
        assert row.severity == CheckSeverity.WARNING  # warn mode -> warning severity
        assert row.file == "src/complex.py"
        assert row.line == 1
        assert "complexity" in row.message.lower()

    def test_rows_equal_to_check_result_of_report_findings(self, tmp_path: Path) -> None:
        """Every row is exactly ``to_check_result`` of the report's findings.

        This pins the shim to the SHARED helper: the rows it returns must be
        byte-for-byte what ``models.to_check_result`` produces over
        ``QualityEvaluator.evaluate(...).findings`` — proving one schema, no
        local re-mapping.
        """
        from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser

        if not TreeSitterParser().is_available():
            pytest.skip("tree-sitter unavailable; complexity pass degrades to skipped")

        _write_project(
            tmp_path,
            {
                "src/complex.py": _high_complexity_source(),
                ".opencontext/quality.toml": 'mode = "warn"\n\n[architecture]\nmax_cc = 1\n',
            },
        )

        from opencontext_core.quality.evaluator import QualityEvaluator

        report = QualityEvaluator(tmp_path).evaluate(["src/complex.py"])
        assert report.findings, "fixture should produce at least one finding"
        expected = [to_check_result(f) for f in report.findings]

        rows = architecture_check_results(tmp_path, ["src/complex.py"])
        assert rows == expected


# --------------------------------------------------------------------------- #
# Folds into generate_report (one schema, two entry points)
# --------------------------------------------------------------------------- #


class TestFoldsIntoGenerateReport:
    def test_clean_rows_count_as_passed_in_report(self, tmp_path: Path) -> None:
        _clean_project(tmp_path)
        rows = architecture_check_results(tmp_path, ["src/a.py"])
        report = CheckRunner(tmp_path).generate_report({ARCHITECTURE_CHECK_NAME: rows})
        summary = report["summary"]
        assert summary["total_checks"] == 1
        assert summary["passed"] == 1
        assert summary["failed"] == 0
        assert summary["success"] is True
        # The report row carries the ci-check schema keys.
        assert set(report["results"][0]) == {
            "check",
            "status",
            "severity",
            "message",
            "file",
            "line",
            "suggestion",
        }

    def test_finding_rows_mark_report_failed(self, tmp_path: Path) -> None:
        """A FAILED finding row makes the folded report ``success=False``."""
        from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser

        if not TreeSitterParser().is_available():
            pytest.skip("tree-sitter unavailable; complexity pass degrades to skipped")

        _write_project(
            tmp_path,
            {
                "src/complex.py": _high_complexity_source(),
                ".opencontext/quality.toml": 'mode = "warn"\n\n[architecture]\nmax_cc = 1\n',
            },
        )
        rows = architecture_check_results(tmp_path, ["src/complex.py"])
        report = CheckRunner(tmp_path).generate_report({ARCHITECTURE_CHECK_NAME: rows})
        assert report["summary"]["success"] is False
        assert report["summary"]["failed"] == 1
        assert report["summary"]["warnings"] >= 1

    def test_coexists_with_pattern_checks_in_one_report(self, tmp_path: Path) -> None:
        """The shim rows + legacy pattern rows share one ``generate_report`` call."""
        _clean_project(tmp_path)
        (tmp_path / "src" / "a.py").write_text(
            "def add(x: int, y: int) -> int:\n    return x + y  # plain\n",
            encoding="utf-8",
        )
        runner = CheckRunner(tmp_path)
        pattern_check = CheckDefinition(
            name="No TODO",
            description="d",
            severity=CheckSeverity.WARNING,
            files=["*.py"],
            patterns=["TODO"],
        )
        pattern_rows = runner.run_check(pattern_check, ["src/a.py"])  # passes (no TODO)
        arch_rows = architecture_check_results(tmp_path, ["src/a.py"])
        report = runner.generate_report(
            {pattern_check.name: pattern_rows, ARCHITECTURE_CHECK_NAME: arch_rows}
        )
        assert report["summary"]["total_checks"] == 2
        assert report["summary"]["success"] is True


# --------------------------------------------------------------------------- #
# Mode off / degrade-honestly
# --------------------------------------------------------------------------- #


class TestModeOffAndDegrade:
    def test_mode_off_yields_passed_row_no_findings(self, tmp_path: Path) -> None:
        """With ``mode = off`` the evaluator returns SKIPPED + no findings.

        The shim then emits a single PASSED representation row (the check is
        present in the report and does not fail) — it never silently vanishes.
        """
        _write_project(
            tmp_path,
            {
                "src/a.py": _high_complexity_source(),  # would be a finding if active
                ".opencontext/quality.toml": 'mode = "off"\n',
            },
        )
        rows = architecture_check_results(tmp_path, ["src/a.py"])
        assert len(rows) == 1
        assert rows[0].status == CheckStatus.PASSED
        assert rows[0].check_name == ARCHITECTURE_CHECK_NAME

    def test_malformed_config_does_not_crash(self, tmp_path: Path) -> None:
        """A broken ``quality.toml`` must not crash ``ci-check run``.

        The evaluator degrades to DEFAULT_RULES on a bad config; the shim must
        therefore still return rows (never raise).
        """
        _write_project(
            tmp_path,
            {
                "src/a.py": "def f() -> int:\n    return 1\n",
                ".opencontext/quality.toml": "this is = not valid = toml ===\n",
            },
        )
        rows = architecture_check_results(tmp_path, ["src/a.py"])
        assert rows and all(isinstance(r, CheckResult) for r in rows)

    def test_evaluation_failure_returns_error_row_not_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unexpected evaluator failure surfaces as one ERROR row, not a raise.

        We monkeypatch ``QualityEvaluator.evaluate`` to blow up and assert the
        shim catches it and degrades honestly (single ERROR ``CheckResult``).
        """
        _clean_project(tmp_path)
        import opencontext_core.quality.evaluator as ev_mod

        def _boom(self, *a: object, **k: object) -> object:
            raise RuntimeError("synthetic evaluator failure")

        monkeypatch.setattr(ev_mod.QualityEvaluator, "evaluate", _boom)
        rows = architecture_check_results(tmp_path, ["src/a.py"])
        assert len(rows) == 1
        assert rows[0].status == CheckStatus.ERROR
        assert rows[0].severity == CheckSeverity.ERROR
        assert "failed" in rows[0].message.lower()


# --------------------------------------------------------------------------- #
# Determinism + zero model calls (the hard contract)
# --------------------------------------------------------------------------- #


class TestDeterministicAndModelFree:
    def test_identical_inputs_yield_identical_rows(self, tmp_path: Path) -> None:
        """Same project + scope -> byte-identical rows (deterministic)."""
        _write_project(
            tmp_path,
            {
                "src/a.py": "def add(x: int, y: int) -> int:\n    return x + y\n",
                "src/b.py": "def sub(x: int, y: int) -> int:\n    return x - y\n",
            },
        )

        def _key(rows: list[CheckResult]) -> list[tuple]:
            return [
                (r.check_name, r.status.value, r.severity.value, r.message, r.file, r.line)
                for r in rows
            ]

        first = architecture_check_results(tmp_path, ["src/a.py", "src/b.py"])
        second = architecture_check_results(tmp_path, ["src/a.py", "src/b.py"])
        assert _key(first) == _key(second)

    def test_no_model_call_in_check_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The check path must invoke NO model/LLM client.

        We trip a tripwire if any known model-invocation seam is touched. The
        deterministic architecture/quality path uses only the graph + parser +
        subprocess tools; touching a model would flip the flag and fail.
        """
        tripped: list[str] = []

        def _trip(name: str):
            def _inner(*a: object, **k: object) -> object:
                tripped.append(name)
                raise AssertionError(f"model call '{name}' in deterministic check path")

            return _inner

        # Patch plausible model/sampling seams *if present* — absence is fine
        # (the point is that none get CALLED). Use raising=False so unknown
        # environments do not error on a missing attribute.
        import opencontext_core.harness.runner as runner_mod

        for attr in ("_sample", "sample", "delegate"):
            monkeypatch.setattr(runner_mod, attr, _trip(attr), raising=False)

        _write_project(
            tmp_path,
            {"src/a.py": _high_complexity_source(), ".opencontext/quality.toml": 'mode = "warn"\n'},
        )
        rows = architecture_check_results(tmp_path, ["src/a.py"])
        assert isinstance(rows, list)
        assert tripped == [], f"model seam(s) invoked: {tripped}"


# --------------------------------------------------------------------------- #
# Isolation: the real ~/.opencontext and repo .opencontext are never touched
# --------------------------------------------------------------------------- #


class TestIsolation:
    def test_baseline_and_config_stay_under_tmp_root(self, tmp_path: Path) -> None:
        """A save-baseline round-trip writes ONLY under the tmp project root.

        ``mode = strict`` + a baseline path proves the persistence layer is
        rooted at the tmp project, never at ``~/.opencontext`` or the repo.
        """
        from opencontext_core.quality.evaluator import QualityEvaluator

        repo_oc_before = _snapshot(_REPO_OC)
        _write_project(
            tmp_path,
            {"src/a.py": "def f() -> int:\n    return 1\n"},
        )
        ev = QualityEvaluator(
            tmp_path, rules=_rules_with_baseline_isolated(tmp_path, mode=QualityMode.STRICT)
        )
        ev.save_baseline()

        baseline = tmp_path / ".opencontext" / "quality-baseline.json"
        assert baseline.exists(), "baseline must be written under the tmp root"
        # The repo's own .opencontext is unchanged by the run.
        assert _snapshot(_REPO_OC) == repo_oc_before

    def test_shim_does_not_write_under_repo_opencontext(self, tmp_path: Path) -> None:
        before = _snapshot(_REPO_OC)
        _write_project(tmp_path, {"src/a.py": _high_complexity_source()})
        architecture_check_results(tmp_path, ["src/a.py"])
        assert _snapshot(_REPO_OC) == before


def _snapshot(directory: Path) -> set[str]:
    """Relative paths under ``directory`` (empty set if absent)."""
    if not directory.exists():
        return set()
    return {p.relative_to(directory).as_posix() for p in directory.rglob("*")}


def _snapshot_with_text(directory: Path) -> dict[str, str | None]:
    """Map relative path -> file text (None for dirs/unreadable) under ``directory``.

    Captures content as well as names so an in-place rewrite is detected, not
    just additions/removals. Absent directory -> empty mapping.
    """
    if not directory.exists():
        return {}
    out: dict[str, str | None] = {}
    for p in directory.rglob("*"):
        rel = p.relative_to(directory).as_posix()
        if p.is_file():
            try:
                out[rel] = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                out[rel] = None
        else:
            out[rel] = None
    return out
