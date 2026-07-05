"""Coherent Quality Result Fields — opencontext_quality result semantics.

Spec: openspec/changes/agent-harness-engineering-hardening/specs/ahe-010-quality-semantics
Pin the three truth classes of the ``opencontext_quality`` MCP tool result so the
report never claims ``success=true`` alongside contradictory signals:

* failed checks imply ``success=false``
* no-applicable checks imply ``status=not_applicable`` with no misleading
  ``failed=N`` count
* clean applicable checks imply ``success=true``

The report dict shape is what ``ci_check.generate_report`` historically
returned (``summary.{total_checks,passed,failed,warnings,errors,success,status}``),
and is also what the QualityReport serializer (``to_report_dict``) emits. The
three classes are produced by the in-process MCP server with a stubbed
language-tool runner so no real linter is required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import opencontext_core.quality.languages as languages_mod
from opencontext_core.mcp_stdio import MCPServer
from opencontext_core.quality.report import QualityReport

_TOOL = "opencontext_quality"

# A 2-file Python import cycle: a -> b -> a. ``DependencyGraphBuilder`` resolves
# ``import b``/``import a`` to ``b.py``/``a.py`` (both in the scanned set), so the
# file-level Tarjan SCC reports exactly one cycle -> one ``max_cycles`` finding.
_A_PY = "import b\n\n\ndef fa():\n    return b.fb()\n"
_B_PY = "import a\n\n\ndef fb():\n    return a.fa()\n"


@pytest.fixture(autouse=True)
def _stub_language_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every language tool report 'missing' without spawning a subprocess.

    Mirrors ``tests/core/test_mcp_quality_tool.py``: only ``_run_tool`` is
    stubbed so the architecture passes run but no real linter is required.
    """

    def _missing(self: object, spec: object, files: object) -> object:
        return languages_mod.ToolRun(
            tool=getattr(spec, "name", "tool"),
            exit_code=-2,
            stdout="",
            stderr="",
            missing=True,
        )

    monkeypatch.setattr(languages_mod.LanguageQualityRunner, "_run_tool", _missing)


def _server(tmp_path: Path) -> MCPServer:
    return MCPServer(
        db_path=tmp_path / ".storage" / "opencontext" / "context_graph.db",
        project_root=tmp_path,
    )


# --------------------------------------------------------------------------- #
# Class 1 — Failed checks imply success=false
# --------------------------------------------------------------------------- #


class TestFailedCheckSemantics:
    """A failing fixture MUST report success=false and a non-zero failed count."""

    def test_cycle_project_reports_success_false(self, tmp_path: Path) -> None:
        """An import-cycle finding must surface as success=false (no fake pass)."""
        (tmp_path / "a.py").write_text(_A_PY, encoding="utf-8")
        (tmp_path / "b.py").write_text(_B_PY, encoding="utf-8")
        server = _server(tmp_path)
        try:
            result = server._call_tool(_TOOL, {"scope": "all"})
        finally:
            server.close()
        assert "error" not in result, result

        data = result["data"]
        summary = data["summary"]
        # Coherent: failed > 0 ↔ success=false. Never both at once.
        assert summary["failed"] >= 1, "cycle fixture must report at least one failed check"
        assert summary["success"] is False, "failed checks must imply success=false"

    def test_cycle_project_status_not_passed(self, tmp_path: Path) -> None:
        """A failed check means the gate is not a clean PASSED."""
        (tmp_path / "a.py").write_text(_A_PY, encoding="utf-8")
        (tmp_path / "b.py").write_text(_B_PY, encoding="utf-8")
        server = _server(tmp_path)
        try:
            result = server._call_tool(_TOOL, {"scope": "all"})
        finally:
            server.close()
        data = result["data"]
        # Under the default warn/ratchet profile the gate is WARNING (advisory
        # surface), not PASSED — it must NOT claim passed when findings exist.
        assert data["status"] in {"warning", "failed"}
        assert data["status"] != "passed"

    def test_no_contradiction_between_failed_and_success(self, tmp_path: Path) -> None:
        """Sanity: failed==0 iff success is allowed to be True.

        The cycle fixture MUST satisfy ``failed > 0`` and ``success is False``
        simultaneously — never ``failed > 0 and success is True`` (the
        contradiction the spec bans).
        """
        (tmp_path / "a.py").write_text(_A_PY, encoding="utf-8")
        (tmp_path / "b.py").write_text(_B_PY, encoding="utf-8")
        server = _server(tmp_path)
        try:
            result = server._call_tool(_TOOL, {"scope": "all"})
        finally:
            server.close()
        data = result["data"]
        failed = data["summary"]["failed"]
        success = data["summary"]["success"]
        assert not (failed > 0 and success is True), (
            f"contradictory report: failed={failed} but success=True; "
            "the spec forbids failed checks with success=true"
        )


# --------------------------------------------------------------------------- #
# Class 2 — No applicable checks imply status=not_applicable, no misleading failed
# --------------------------------------------------------------------------- #


class TestNoApplicableCheckSemantics:
    """A no-applicable-checks fixture MUST report not_applicable with failed=0."""

    def test_empty_project_reports_not_applicable(self, tmp_path: Path) -> None:
        """A project with no source files yields status=not_applicable.

        No code -> no findings -> no skipped rules -> ``applicable = passed +
        failed = 0``. The serializer MUST classify this as ``not_applicable``,
        not invent a misleading passed/failed tally.
        """
        # tmp_path is empty: no source at all.
        server = _server(tmp_path)
        try:
            result = server._call_tool(_TOOL, {"scope": "all"})
        finally:
            server.close()
        assert "error" not in result, result

        data = result["data"]
        # Top-level status field (the spec asks for ``status`` exactly).
        msg = (
            f"no-applicable-checks fixture must report "
            f"status='not_applicable', got {data['status']!r}"
        )
        assert data["status"] == "not_applicable", msg
        # Mirrored under summary for the ci_checks-compatible contract.
        assert data["summary"]["status"] == "not_applicable"

    def test_empty_project_failed_count_is_zero_not_misleading(self, tmp_path: Path) -> None:
        """The not_applicable case MUST NOT report a misleading failed=N>0.

        A reader must be able to distinguish "no checks ran" from "checks ran
        and some failed". ``failed=0`` here is the honest signal: no findings,
        because no checks were applicable.
        """
        server = _server(tmp_path)
        try:
            result = server._call_tool(_TOOL, {"scope": "all"})
        finally:
            server.close()
        data = result["data"]
        # Explicit assertion per the spec wording.
        assert data["summary"]["failed"] == 0, (
            "not_applicable must not report a misleading failed=N>0 count"
        )
        assert data["summary"]["passed"] == 0
        assert data["summary"]["total_checks"] == 0

    def test_empty_project_does_not_pretend_success(self, tmp_path: Path) -> None:
        """No-applicable must NOT report success=true either.

        A reader that branches on ``summary.success`` alone would treat an
        empty repo as a green light — that's the false-pass surface the spec
        explicitly bans. The no-applicable verdict is neither passed nor
        failed; it is "nothing was measured". The report therefore MUST mark
        ``success=False`` (or otherwise disambiguate from a real pass).
        """
        server = _server(tmp_path)
        try:
            result = server._call_tool(_TOOL, {"scope": "all"})
        finally:
            server.close()
        data = result["data"]
        # The decisive assertion: not_applicable must NOT report success=true.
        assert data["summary"]["success"] is False, (
            "not_applicable must not claim success=true; the spec forbids "
            "contradictory fields (no failed AND no passed yet success=true)"
        )


# --------------------------------------------------------------------------- #
# Class 3 — Clean applicable checks imply success=true
#
# The clean-applicable class is pinned at the unit level by constructing a
# QualityReport directly: the in-process MCP path with the autouse stubbed
# language tools degrades every language rule to SKIPPED, so a clean solo.py
# ends up with ``applicable == 0`` (not_applicable) — that's the "no
# applicable checks" class above. To pin the green gate specifically we build
# a QualityReport whose verdicts contain at least one PASSED entry and no
# FAILED entry; the success formula must then be True.
# --------------------------------------------------------------------------- #


class TestCleanApplicableSemantics:
    """When applicable rules run AND pass, ``success=True`` and status=passed."""

    def _clean_quality_report(self) -> QualityReport:
        """Build a QualityReport that has run clean (one PASSED architecture verdict)."""
        from opencontext_core.harness.models import GateStatus
        from opencontext_core.quality.ci_checks import CheckSeverity, CheckStatus
        from opencontext_core.quality.models import (
            HealthScore,
            QualityMetrics,
            QualityReport,
            RuleVerdict,
        )

        metrics = QualityMetrics()
        health = HealthScore(score=10000, metrics=metrics, components={})
        verdict = RuleVerdict(
            rule="max_cycles",
            status=CheckStatus.PASSED,
            severity=CheckSeverity.INFO,
            findings=(),
            message="0 cycles detected",
        )
        return QualityReport(
            status=GateStatus.PASSED,
            findings=(),
            verdicts=(verdict,),
            health=health,
        )

    def test_synthetic_clean_report_reports_success_true(self) -> None:
        """A QualityReport with a PASSED verdict and 0 failed emits success=True."""
        report = self._clean_quality_report()
        d = report.to_report_dict()
        assert d["status"] == "passed"
        assert d["summary"]["passed"] == 1
        assert d["summary"]["failed"] == 0
        assert d["summary"]["success"] is True

    def test_synthetic_failed_report_reports_success_false(self) -> None:
        """A QualityReport with a FAILED verdict emits success=False (regression pin)."""
        from opencontext_core.harness.models import GateStatus
        from opencontext_core.quality.ci_checks import CheckSeverity, CheckStatus
        from opencontext_core.quality.models import (
            Finding,
            HealthScore,
            QualityMetrics,
            QualityReport,
            RuleVerdict,
        )

        finding = Finding(
            rule="max_cycles",
            severity=CheckSeverity.ERROR,
            message="Import cycle",
        )
        verdict = RuleVerdict(
            rule="max_cycles",
            status=CheckStatus.FAILED,
            severity=CheckSeverity.ERROR,
            findings=(finding,),
            message="1 finding",
        )
        report = QualityReport(
            status=GateStatus.WARNING,
            findings=(finding,),
            verdicts=(verdict,),
            health=HealthScore(score=9600, metrics=QualityMetrics(), components={"cycles": 400}),
        )
        d = report.to_report_dict()
        assert d["summary"]["failed"] == 1
        assert d["summary"]["success"] is False
        assert d["status"] == "warning"

    def test_synthetic_no_applicable_report_reports_status_not_applicable(self) -> None:
        """A QualityReport with no verdicts at all emits status=not_applicable."""
        from opencontext_core.harness.models import GateStatus
        from opencontext_core.quality.models import (
            HealthScore,
            QualityMetrics,
            QualityReport,
        )

        report = QualityReport(
            status=GateStatus.PASSED,
            findings=(),
            verdicts=(),
            health=HealthScore(score=10000, metrics=QualityMetrics(), components={}),
        )
        d = report.to_report_dict()
        assert d["status"] == "not_applicable"
        assert d["summary"]["failed"] == 0
        assert d["summary"]["success"] is False


# --------------------------------------------------------------------------- #
# Audit fixture — capture the contradictory cases in one test (Task 9.1)
# --------------------------------------------------------------------------- #


class TestQualityAuditFixture:
    """The spec's audit fixture: capture every contradictory case in one place.

    Three classes are pinned simultaneously so a future change that flips one
    without the others fails immediately.
    """

    @pytest.fixture
    def reports(self, tmp_path: Path) -> dict[str, dict]:
        # Failed: import cycle.
        (tmp_path / "a.py").write_text(_A_PY, encoding="utf-8")
        (tmp_path / "b.py").write_text(_B_PY, encoding="utf-8")
        cycle_server = _server(tmp_path)
        cycle_report = cycle_server._call_tool(_TOOL, {"scope": "all"})["data"]
        cycle_server.close()

        # Not-applicable: empty project in a separate tmp dir (subdir keeps it
        # isolated from the cycle's source files).
        empty = tmp_path / "_empty"
        empty.mkdir()
        empty_server = _server(empty)
        empty_report = empty_server._call_tool(_TOOL, {"scope": "all"})["data"]
        empty_server.close()

        # Clean: single-file project in another isolated dir.
        clean = tmp_path / "_clean"
        clean.mkdir()
        (clean / "solo.py").write_text("def only():\n    return 1\n", encoding="utf-8")
        clean_server = _server(clean)
        clean_report = clean_server._call_tool(_TOOL, {"scope": "all"})["data"]
        clean_server.close()

        return {
            "failed": cycle_report,
            "not_applicable": empty_report,
            "passed": clean_report,
        }

    def test_audit_no_class_contradicts_itself(self, reports: dict[str, dict]) -> None:
        """Across all three classes: failed>0 ↛ success=true, never the reverse."""
        for label, report in reports.items():
            failed = report["summary"]["failed"]
            success = report["summary"]["success"]
            assert not (failed > 0 and success is True), (
                f"{label} report contradicts itself: failed={failed} but success=True"
            )

    def test_audit_failed_class_invariants(self, reports: dict[str, dict]) -> None:
        failed = reports["failed"]
        assert failed["summary"]["failed"] >= 1
        assert failed["summary"]["success"] is False
        assert failed["status"] != "passed"
        assert failed["status"] != "not_applicable"

    def test_audit_not_applicable_class_invariants(self, reports: dict[str, dict]) -> None:
        na = reports["not_applicable"]
        assert na["status"] == "not_applicable"
        assert na["summary"]["status"] == "not_applicable"
        assert na["summary"]["failed"] == 0
        assert na["summary"]["success"] is False, (
            "the audit fixture pins the contradictory surface: a not_applicable "
            "report that also claims success=True must fail this test"
        )
