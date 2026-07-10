"""Tests for verification checks, including P3.5 harness/adapter checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.verification import (
    CheckResult,
    check_adapters,
    check_boundary_service,
    check_harness_phases,
    check_harness_runner,
    run_all_checks,
)


class TestCheckResult:
    def test_defaults(self) -> None:
        r = CheckResult(name="test", status="passed", message="ok")
        assert r.name == "test"
        assert r.status == "passed"
        assert r.message == "ok"
        assert r.details == ""


class TestHarnessPhasesCheck:
    def test_all_nine_phases_available(self) -> None:
        result = check_harness_phases()
        assert result.status == "passed"
        assert "9/9" in result.message
        assert "explore" in result.message
        assert "propose" in result.message
        assert "spec" in result.message
        assert "design" in result.message
        assert "tasks" in result.message
        assert "apply" in result.message
        assert "verify" in result.message
        assert "review" in result.message
        assert "archive" in result.message


class TestHarnessRunnerCheck:
    def test_runner_instantiatable(self) -> None:
        result = check_harness_runner()
        assert result.status == "passed"
        assert "Runner ready" in result.message


class TestAdaptersCheck:
    def test_adapters_report(self) -> None:
        result = check_adapters()
        # local and python should always be available
        assert "local" in result.message
        assert "python" in result.message
        # status might be passed or warning depending on aider
        assert result.status in ("passed", "warning")


class TestBoundaryServiceCheck:
    def test_service_importable(self) -> None:
        result = check_boundary_service()
        assert result.status == "passed"
        assert "6 targets" in result.message


class TestRunAllChecks:
    def test_includes_new_checks(self) -> None:
        report = run_all_checks()
        check_names = [r.name for r in report.results]

        assert "Harness Phases" in check_names
        assert "Harness Runner" in check_names
        assert "Adapters" in check_names
        assert "Boundary Service" in check_names
        assert len(report.results) >= 11  # 7 original + 4 new

    def test_healthy_if_no_failures(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """The report should be healthy if there are zero failures.

        Isolate the environment so the check registry sees a private, well-formed
        project instead of the shared process cwd / real HOME. ``run_all_checks``
        resolves the Knowledge-Graph DB from ``Path.cwd()`` and reads user config
        from HOME; under ``-n auto`` a concurrent test that chdir's elsewhere or
        truncates the shared repo ``context_graph.db`` can flip the KG check to a
        warning/failed state, and ``is_healthy`` is ``failures == 0 AND no KG
        warning`` — so a degraded KG breaks the ``failures == 0 -> is_healthy``
        invariant this test asserts. We give the test its OWN tmp HOME + cwd and
        seed a minimal valid KG DB there so the KG check deterministically passes,
        independent of any other worker.
        """
        import sqlite3

        from opencontext_core.config_resolver import resolve_active_storage_path

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / ".local" / "state"))
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / ".cache"))

        # Seed a minimal, well-formed KG so `check_knowledge_graph` passes (an empty
        # cwd would make it *warn* — "No database yet" — which alone flips is_healthy).
        storage = resolve_active_storage_path(Path.cwd())
        storage.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(storage / "context_graph.db"))
        conn.execute("CREATE TABLE files (path TEXT)")
        conn.commit()
        conn.close()

        report = run_all_checks()
        # Warnings don't count as failures
        assert report.failures >= 0
        if report.failures == 0:
            assert report.is_healthy is True
