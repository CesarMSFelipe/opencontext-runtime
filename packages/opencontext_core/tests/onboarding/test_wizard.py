"""RED-first tests for the curated first-run wizard (PR-R2-D).

Spec: openspec/changes/opencontext-1-0-convergence/specs/developer-experience-onboarding/spec.md

The wizard is the programmatic, opinionated 4-step first-run journey
(detect_stack → configure → index → verify). It composes the existing
``OnboardingService`` but exposes a step-by-step API so callers (CLI,
``opencontext init --wizard``, ``opencontext status --onboarding``) can
report progress and resume from any step.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from opencontext_core.onboarding.checklist import DxChecklist, run_checklist
from opencontext_core.onboarding.metrics import DxMetrics
from opencontext_core.onboarding.wizard import (
    OnboardingWizard,
    WizardReport,
    WizardStep,
    run_onboarding,
)

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeStack:
    """Result of detect_stack — minimal shape the wizard consumes."""

    language: str = "python"
    framework: str | None = None
    package_manager: str | None = None
    entrypoints: tuple[str, ...] = ()


class _FakeService:
    """Stand-in for OnboardingService used in wizard tests.

    The wizard depends on the service's behaviour; we want each step to
    progress independently so the wizard's own step API is what we cover
    here. Integration with the real service is covered by service tests.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, options: Any) -> Any:
        from opencontext_core.onboarding.service import OnboardingResult

        self.calls.append(("run", {"root": str(options.root), "template": options.template}))
        # Write a config the wizard can verify in step 4.
        config_path = options.root / "opencontext.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("project: {}\n", encoding="utf-8")
        return OnboardingResult(
            root=str(options.root),
            config_path=str(config_path),
            indexed_files=3,
            indexed_symbols=12,
            knowledge_graph_nodes=2,
            knowledge_graph_edges=1,
            active_clients=list(options.active_clients),
            generated_agent_files=[],
            sdd_context_path=str(options.root / ".opencontext" / "sdd" / "context.json"),
            harness_config_path=str(options.root / ".opencontext" / "harness.yaml"),
        )


@pytest.fixture
def fake_service(monkeypatch: pytest.MonkeyPatch) -> _FakeService:
    svc = _FakeService()
    monkeypatch.setattr("opencontext_core.onboarding.wizard.OnboardingService", lambda: svc)
    return svc


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """A clean project directory with a single Python file."""

    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("def hello() -> str:\n    return 'hi'\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# WizardStep enum
# ---------------------------------------------------------------------------


class TestWizardStep:
    def test_wizard_step_has_exactly_four_values(self) -> None:
        assert {s.name for s in WizardStep} == {
            "DETECT_STACK",
            "CONFIGURE",
            "INDEX",
            "VERIFY",
        }

    def test_wizard_step_order_matches_journey(self) -> None:
        ordered = [
            WizardStep.DETECT_STACK,
            WizardStep.CONFIGURE,
            WizardStep.INDEX,
            WizardStep.VERIFY,
        ]
        assert list(WizardStep) == ordered


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestOnboardingWizardConstruction:
    def test_default_root_is_current_directory(self) -> None:
        wizard = OnboardingWizard()
        assert wizard.root == Path(".").resolve()

    def test_root_is_resolved_to_absolute_path(self, tmp_path: Path) -> None:
        wizard = OnboardingWizard(root=tmp_path)
        assert wizard.root == tmp_path.resolve()

    def test_default_steps_sequence_is_the_4_step_journey(self) -> None:
        wizard = OnboardingWizard()
        assert [s.name for s in wizard.steps] == [
            "DETECT_STACK",
            "CONFIGURE",
            "INDEX",
            "VERIFY",
        ]


# ---------------------------------------------------------------------------
# Step 1: detect_stack
# ---------------------------------------------------------------------------


class TestDetectStack:
    def test_detect_stack_identifies_python_project(self, empty_project: Path) -> None:
        wizard = OnboardingWizard(root=empty_project)
        stack = wizard.detect_stack()
        assert stack.language == "python"
        assert stack.entrypoints  # at least one .py file was found

    def test_detect_stack_identifies_node_project(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        (tmp_path / "index.js").write_text("module.exports = {};\n", encoding="utf-8")
        wizard = OnboardingWizard(root=tmp_path)
        stack = wizard.detect_stack()
        assert stack.language == "javascript"
        assert stack.package_manager is None  # no lockfile yet

    def test_detect_stack_with_no_source_files(self, tmp_path: Path) -> None:
        wizard = OnboardingWizard(root=tmp_path)
        stack = wizard.detect_stack()
        assert stack.language == "unknown"
        assert stack.entrypoints == ()

    def test_detect_stack_records_step_result(self, empty_project: Path) -> None:
        wizard = OnboardingWizard(root=empty_project)
        wizard.detect_stack()
        record = wizard.step_records[WizardStep.DETECT_STACK]
        assert record.status == "ok"
        assert "language" in record.summary


# ---------------------------------------------------------------------------
# Step 2: configure
# ---------------------------------------------------------------------------


class TestConfigureStep:
    def test_configure_writes_opencontext_yaml(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        wizard = OnboardingWizard(root=empty_project)
        wizard.detect_stack()
        result = wizard.configure(template="generic", security_mode="private_project")
        # configure is in-place AND returns the underlying OnboardingResult so
        # callers can chain (e.g. ``wizard.index()`` reads it back).
        assert result is not None
        assert (empty_project / "opencontext.yaml").exists()
        # Service was invoked exactly once with the expected options.
        assert len(fake_service.calls) == 1
        assert fake_service.calls[0][0] == "run"
        assert fake_service.calls[0][1]["template"] == "generic"

    def test_configure_marks_step_done(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        wizard = OnboardingWizard(root=empty_project)
        wizard.configure()
        assert wizard.step_records[WizardStep.CONFIGURE].status == "ok"


# ---------------------------------------------------------------------------
# Step 3: index
# ---------------------------------------------------------------------------


class TestIndexStep:
    def test_index_uses_configured_service_result(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        wizard = OnboardingWizard(root=empty_project)
        wizard.configure()
        manifest = wizard.index()
        assert manifest.indexed_files == 3
        assert manifest.indexed_symbols == 12
        assert wizard.step_records[WizardStep.INDEX].status == "ok"

    def test_index_can_run_standalone_after_configure(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        wizard = OnboardingWizard(root=empty_project)
        # configure step is required first.
        wizard.configure()
        manifest = wizard.index()
        assert manifest.config_path.endswith("opencontext.yaml")


# ---------------------------------------------------------------------------
# Step 4: verify
# ---------------------------------------------------------------------------


class TestVerifyStep:
    def test_verify_returns_wizard_report(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        wizard = OnboardingWizard(root=empty_project)
        wizard.configure()
        wizard.index()
        report = wizard.verify()
        assert isinstance(report, WizardReport)
        assert report.config_exists is True
        assert report.checklist_score >= 0
        assert report.checklist_score <= 100

    def test_verify_fails_when_config_missing(
        self, tmp_path: Path, fake_service: _FakeService
    ) -> None:
        # No configure() → no opencontext.yaml on disk.
        wizard = OnboardingWizard(root=tmp_path)
        report = wizard.verify()
        assert report.config_exists is False
        assert report.checklist_score < 100


# ---------------------------------------------------------------------------
# Full run_onboarding entry point
# ---------------------------------------------------------------------------


class TestRunOnboarding:
    def test_run_executes_all_four_steps_in_order(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        report = run_onboarding(empty_project, template="generic")
        # Service was called exactly once (by configure step).
        assert len(fake_service.calls) == 1
        assert report.checklist_score > 0
        # Every step ended up in the "ok" status — check the report's
        # step_records (the wizard instance inside run_onboarding is local).
        for step, record in report.step_records.items():
            assert record.status == "ok", (
                f"step {step.name!s} ended in {record.status!r}, expected 'ok'"
            )

    def test_run_returns_wizard_report(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        report = run_onboarding(empty_project)
        assert isinstance(report, WizardReport)
        assert report.root == empty_project.resolve()

    def test_run_records_timing_per_step(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        report = run_onboarding(empty_project)
        # Each step's duration must be a non-negative number.
        for step_record in report.step_records.values():
            assert step_record.duration_seconds >= 0

    def test_run_with_explicit_kwargs(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        run_onboarding(
            empty_project,
            template="enterprise",
            security_mode="enterprise",
            active_clients=["opencode"],
        )
        assert fake_service.calls[0][1]["template"] == "enterprise"

    def test_run_default_root_is_cwd(
        self, monkeypatch: pytest.MonkeyPatch, fake_service: _FakeService
    ) -> None:
        monkeypatch.chdir(fake_service.calls[0][1].get("root", ".") if fake_service.calls else ".")
        # Run with no root → uses "." which resolves.
        report = run_onboarding()
        assert report.root == Path(".").resolve()


# ---------------------------------------------------------------------------
# WizardReport + DxChecklist + DxMetrics integration
# ---------------------------------------------------------------------------


class TestWizardReportComposition:
    def test_report_includes_dx_metrics(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        report = run_onboarding(empty_project)
        assert isinstance(report.metrics, DxMetrics)
        assert report.metrics.time_to_first_context_seconds >= 0

    def test_report_checklist_score_matches_run_checklist(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        report = run_onboarding(empty_project)
        checklist = run_checklist(empty_project)
        assert isinstance(checklist, DxChecklist)
        assert report.checklist_score == checklist.score

    def test_failed_configure_propagates_to_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A service that raises: the wizard must mark CONFIGURE as failed and
        # not crash the full journey — verify() reports the partial state.

        def _boom(self: Any) -> Any:
            raise RuntimeError("config boom")

        monkeypatch.setattr("opencontext_core.onboarding.wizard.OnboardingService", _boom)

        report = run_onboarding(tmp_path)
        # Configure step should be marked failed, verify should still produce
        # a report (with a low checklist score because the config is missing).
        assert report.checklist_score < 100
        assert report.config_exists is False


# ---------------------------------------------------------------------------
# Resume from a specific step
# ---------------------------------------------------------------------------


class TestResume:
    def test_resume_from_step_skips_earlier_steps(
        self, empty_project: Path, fake_service: _FakeService
    ) -> None:
        wizard = OnboardingWizard(root=empty_project)
        # Pretend configure already ran.
        wizard.detect_stack()
        wizard.configure()
        before = len(fake_service.calls)

        # Resume from INDEX — configure must NOT be called again.
        manifest = wizard.run_from(WizardStep.INDEX)
        assert manifest is not None
        assert len(fake_service.calls) == before
        assert wizard.step_records[WizardStep.INDEX].status == "ok"

    def test_run_from_unknown_step_raises(self, empty_project: Path) -> None:
        wizard = OnboardingWizard(root=empty_project)
        with pytest.raises(ValueError):
            wizard.run_from("BOGUS")  # type: ignore[arg-type]
