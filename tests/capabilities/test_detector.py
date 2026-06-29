"""build_capability_graph reuses existing detection without duplicating it (CP-004)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.capabilities.detector import STRICT_HARNESS, build_capability_graph
from opencontext_core.sdd_runtime import detect_test_capabilities


def _node_ids(root: Path) -> set[str]:
    return {n.id for n in build_capability_graph(root).nodes}


def test_python_project_yields_pytest_and_ruff_with_evidence(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    graph = build_capability_graph(tmp_path)
    by_id = {n.id: n for n in graph.nodes}

    assert "pytest" in by_id
    assert "ruff-check" in by_id
    assert by_id["pytest"].available is True
    assert by_id["pytest"].evidence != ""
    assert by_id["pytest"].kind == "test"
    assert by_id["ruff-check"].kind == "lint"


def test_empty_project_yields_no_test_or_lint_nodes_and_does_not_raise(tmp_path: Path) -> None:
    graph = build_capability_graph(tmp_path)

    test_lint = [n for n in graph.nodes if n.kind in {"test", "lint", "type"}]
    assert test_lint == []  # no tooling markers -> no tooling nodes


def test_detector_reuses_detect_test_capabilities_one_to_one(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")

    detected = {c.name: c for c in detect_test_capabilities(tmp_path)}
    by_id = {n.id: n for n in build_capability_graph(tmp_path).nodes}

    # Every detected tooling capability appears as a node with identical evidence
    # (the detector lifts the existing facts, it does not re-detect them).
    for name, cap in detected.items():
        assert name in by_id, f"detector dropped {name}"
        assert by_id[name].evidence == cap.evidence


def test_strict_harness_node_depends_on_pytest(tmp_path: Path) -> None:
    graph = build_capability_graph(tmp_path)
    harness = graph.get(STRICT_HARNESS)
    assert harness is not None
    assert harness.depends_on == ["pytest"]
    # Empty project: no pytest -> strict harness is not ready (graceful, CP-005).
    assert graph.is_ready(STRICT_HARNESS) is False


def test_provider_node_present(tmp_path: Path) -> None:
    graph = build_capability_graph(tmp_path)
    assert any(n.kind == "provider" for n in graph.nodes)
