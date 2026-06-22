"""Regression tests for the definitive interconnection-review fixes.

Pins the two HIGH-severity broken LIVE loops the review confirmed:
  - #1 CI surface: `opencontext ci-check run` folds in the architecture/quality evaluation.
  - #2 producer handoff: HarnessRunResult carries context_omitted_paths so the memory
    harvester records them as FAILURE linked_nodes (the recent_failure boost source).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.memory.harvester import MemoryHarvester
from opencontext_core.models.agent_memory import MemoryLayer


@dataclass
class FakeResult:
    run_id: str = "run-omit-1"
    task: str = "add caching to auth"
    status: str = "passed"
    gates: list = field(default_factory=list)
    ledgers: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    context_omitted_paths: list = field(default_factory=list)


def make_store() -> LocalMemoryStore:
    tmpdir = tempfile.mkdtemp()
    return LocalMemoryStore(Path(tmpdir) / "mem.db")


def test_harness_run_result_carries_omitted_paths_field() -> None:
    """The field must exist on HarnessRunResult or the harvester's source-1 is dead."""
    from opencontext_core.harness.models import HarnessRunResult

    result = HarnessRunResult(run_id="r", workflow="w", task="t", status=None)  # type: ignore[arg-type]
    assert hasattr(result, "context_omitted_paths")
    assert result.context_omitted_paths == []


def test_omitted_paths_flow_to_failure_linked_nodes() -> None:
    """#2: omitted paths on the result become FAILURE linked_nodes (boost source)."""
    store = make_store()
    harvester = MemoryHarvester(store)
    result = FakeResult(context_omitted_paths=["src/auth.py:10", "validate_token"])

    records = harvester.harvest(result)

    failure = [r for r in records if r.layer == MemoryLayer.FAILURE]
    assert failure, "omitted paths must produce a FAILURE record for the recent_failure boost"
    linked = failure[0].linked_nodes
    assert "src/auth.py:10" in linked
    # a bare symbol name is normalized to a synthetic file id, never dropped
    assert any("validate_token" in node for node in linked)


def test_no_omitted_paths_writes_no_failure_record() -> None:
    """Guard: a clean run (no omissions) must not spam FAILURE records."""
    store = make_store()
    harvester = MemoryHarvester(store)
    records = harvester.harvest(FakeResult(context_omitted_paths=[]))
    assert not [r for r in records if r.layer == MemoryLayer.FAILURE]


def test_ci_check_run_folds_in_architecture_quality(monkeypatch, tmp_path, capsys) -> None:
    """#1: the `run` report must surface the architecture/quality evaluation.

    Asserts the observable outcome (the rendered report includes the check) rather
    than spying on the lazy import, so it is robust to suite ordering.
    """
    import json

    from opencontext_cli.commands import ci_check_cmd
    from opencontext_core.quality.ci_checks import ARCHITECTURE_CHECK_NAME

    monkeypatch.chdir(tmp_path)
    args = SimpleNamespace(
        ci_check_command="run",
        file=None,
        json=True,
        name=None,
        suite=str(tmp_path / "none.yaml"),
        config=None,
        no_refresh=True,
    )

    ci_check_cmd.handle_ci_check(args)

    report = json.loads(capsys.readouterr().out)
    names = [row.get("check") for row in report.get("results", [])]
    assert ARCHITECTURE_CHECK_NAME in names, (
        f"ci-check run must surface the architecture/quality check; got {names}"
    )


def test_quality_check_records_evolution(tmp_path) -> None:
    """Phase 3: `quality check` appends to the evolution log (built but was unwired)."""
    import json

    import pytest

    from opencontext_cli.commands import quality_cmd

    args = SimpleNamespace(path=str(tmp_path), json=True, diff=False)
    # handle_quality_check raises SystemExit(exit_code) by CLI convention; the
    # evolution append happens before the exit.
    with pytest.raises(SystemExit):
        quality_cmd.handle_quality_check(args)

    root = Path(str(tmp_path)).resolve()
    evo = root / ".opencontext" / "quality-evolution.json"
    assert evo.exists(), "quality check must append to the evolution log across runs"
    rows = json.loads(evo.read_text())
    assert rows and "score" in rows[0]


def test_dedup_collapses_same_symbol_when_symbol_name_blank() -> None:
    """P7: symbol_kind set but symbol name blank must still collapse by source line.

    Previously _key_for_dedup returned (file, "") and the empty-key guard skipped
    secondary dedup (under-dedup), so the same symbol from two sources survived.
    """
    from opencontext_core.models.context import (
        ContextItem,
        ContextPriority,
        DataClassification,
    )
    from opencontext_core.retrieval.planner import _deduplicate

    def _item(item_id: str, source_type: str, content: str) -> ContextItem:
        return ContextItem(
            id=item_id,
            content=content,
            source="src/auth.py:54",
            source_type=source_type,
            priority=ContextPriority.P2,
            tokens=5,
            score=0.7,
            metadata={"symbol_kind": "function", "symbol": ""},
            classification=DataClassification.INTERNAL,
            source_trust=0.8,
        )

    items = [
        _item("fts:x", "fts", "short"),
        _item("graph:y", "graph", "the full longer body"),
    ]
    out = _deduplicate(items)
    assert len(out) == 1, "same symbol/line from two sources must collapse to one"
    assert out[0].content == "the full longer body", "richest-body copy must win"


def test_normalize_linked_node_keeps_bare_path_matchable() -> None:
    """P14: a bare relative path must NOT get a ``:0`` suffix (it breaks the boost match)."""
    from opencontext_core.memory.harvester import _normalize_linked_node

    assert _normalize_linked_node("src/auth.py") == "src/auth.py"  # not "src/auth.py:0"
    assert _normalize_linked_node("src/auth.py:54") == "src/auth.py:54"  # path:line as-is
    assert _normalize_linked_node("validate_token") == "validate_token.py:0"  # bare symbol
