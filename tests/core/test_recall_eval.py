"""Honest retrieval eval: runs the real retriever and measures recall/tokens/latency."""

from __future__ import annotations

from pathlib import Path

from conftest import create_sample_project, write_config
from opencontext_core.evaluation.recall_eval import (
    RecallTask,
    format_recall_report,
    run_recall_eval,
)
from opencontext_core.runtime import OpenContextRuntime


def _runtime(tmp_path: Path) -> tuple[OpenContextRuntime, Path]:
    project = tmp_path / "project"
    project.mkdir()
    create_sample_project(project)  # writes src/auth.py (login, audit_login) + README
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project),
        storage_path=tmp_path / ".storage/opencontext",
    )
    runtime.index_project(project)
    return runtime, project


def test_recall_eval_measures_real_retrieval(tmp_path: Path) -> None:
    runtime, project = _runtime(tmp_path)
    tasks = [
        RecallTask(
            id="auth",
            query="how does authentication login work",
            relevant_files=["src/auth.py"],
        ),
    ]

    report = run_recall_eval(runtime, tasks, project)

    assert len(report.results) == 1
    r = report.results[0]
    # The retriever actually found the relevant file (not assumed).
    assert r.recall == 1.0
    assert "src/auth.py" in r.found
    assert r.pack_tokens > 0
    # token_ratio is real (pack vs the dir-baseline) — on a 1-file toy project the
    # pack's framing can exceed the lone source file; the point is it is MEASURED,
    # not assumed. On real repos the dir-baseline dominates.
    assert r.baseline_tokens > 0 and r.token_ratio > 0
    assert r.latency_ms >= 0.0
    assert "mean recall" in format_recall_report(report)


def test_recall_eval_reports_misses_honestly(tmp_path: Path) -> None:
    runtime, project = _runtime(tmp_path)
    # A file the project does not contain -> recall must drop, not be assumed 100%.
    tasks = [
        RecallTask(
            id="missing",
            query="payment gateway webhook retry",
            relevant_files=["src/payments/gateway.py"],
        ),
    ]

    report = run_recall_eval(runtime, tasks, project)
    r = report.results[0]
    assert r.recall == 0.0
    assert "src/payments/gateway.py" in r.missing
