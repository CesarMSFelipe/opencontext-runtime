"""Task-end KG rebuild: the graph must reflect the task's working-tree changes."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from opencontext_core.config import default_config_data
from opencontext_core.harness.runner import HarnessRunner, HarnessState
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.runtime import OpenContextRuntime


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, capture_output=True)


def test_git_changed_files_detects_untracked(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "a.py").write_text("def x():\n    return 1\n", encoding="utf-8")
    assert "a.py" in HarnessRunner._git_changed_files(tmp_path)


def test_post_run_update_rebuilds_kg_with_task_changes(tmp_path: Path) -> None:
    # No apply_edits are recorded (host-driven), so the rebuild must come from the
    # working-tree diff: a symbol added during the task must land in the graph.
    _git_init(tmp_path)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "opencontext.yaml").write_text(
        yaml.safe_dump(default_config_data()), encoding="utf-8"
    )
    runtime = OpenContextRuntime(
        config_path=str(tmp_path / "opencontext.yaml"),
        storage_path=tmp_path / ".storage" / "opencontext",
    )
    runtime.index_project(tmp_path)

    # The "task" adds a new function — written to the tree, not via apply_edits.
    (tmp_path / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
        encoding="utf-8",
    )

    runner = HarnessRunner(root=tmp_path)
    runner._post_run_update(HarnessState(run_id="r1", root=tmp_path, task="add subtract"))

    kg = KnowledgeGraph(db_path=tmp_path / ".storage" / "opencontext" / "context_graph.db")
    hits = kg.search("subtract")
    kg.close()
    assert hits, "KG was not rebuilt with the task's new symbol"


def test_explore_propagates_trace_id_so_propose_gate_passes(tmp_path: Path) -> None:
    # Regression: no phase set result.trace_id, so state.trace_ids stayed empty and
    # propose's declared 'trace_id_created' gate ALWAYS failed (every run showed
    # PROPOSE failed though the proposal was fine). Explore now propagates the
    # persisted retrieval trace id.
    from opencontext_core.harness.models import GateStatus

    _git_init(tmp_path)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "opencontext.yaml").write_text(
        yaml.safe_dump(default_config_data()), encoding="utf-8"
    )
    runtime = OpenContextRuntime(
        config_path=str(tmp_path / "opencontext.yaml"),
        storage_path=tmp_path / ".storage" / "opencontext",
    )
    runtime.index_project(tmp_path)

    result = HarnessRunner(root=tmp_path).run("standard", "add a subtract function")

    assert result.trace_ids, "the run recorded at least one retrieval trace"
    trace_gates = [g for g in result.gates if g.id == "trace_id_created"]
    assert trace_gates, "propose declares a trace_id_created gate"
    assert all(g.status == GateStatus.PASSED for g in trace_gates)


def test_run_records_acon_feedback_outcome_with_omissions(tmp_path: Path, monkeypatch) -> None:
    # ACON-lite needs the outcome and the retrieval omissions co-recorded on one
    # operation. A harness run must record a 'context_pack' metric with success set
    # (not None) so the token optimizer can later widen the budget.
    from opencontext_core.learning.feedback_collector import FeedbackCollector

    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    _git_init(tmp_path)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "opencontext.yaml").write_text(
        yaml.safe_dump(default_config_data()), encoding="utf-8"
    )
    runtime = OpenContextRuntime(
        config_path=str(tmp_path / "opencontext.yaml"),
        storage_path=tmp_path / ".storage" / "opencontext",
    )
    runtime.index_project(tmp_path)

    HarnessRunner(root=tmp_path).run("standard", "add a subtract function")

    fb = FeedbackCollector(storage_path=tmp_path / ".storage" / "opencontext" / "learning")
    metrics = fb.load_metrics(operation_type="context_pack")
    assert metrics, "the run recorded a context_pack feedback metric"
    # success is co-recorded with the run (True/False, never left None).
    assert metrics[0].success is not None
