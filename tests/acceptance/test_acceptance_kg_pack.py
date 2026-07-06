"""AC-005..AC-008 / AC-020 / AC-021: knowledge graph, pack relevance, budgets.

Contracts: KG_CONTEXT_COMPRESSION_CONTRACT.md, ACCEPTANCE_CONTRACT.md.
"""

from __future__ import annotations

import pytest

from tests.acceptance.helpers.cli import run_json
from tests.acceptance.helpers.ops import index_workspace, install_workspace

pytestmark = pytest.mark.acceptance

_QUERY = "fix the multiply_values bug in calculator"


def _pack(oc_bin, ws, *extra: str) -> dict:
    proc, payload = run_json(
        oc_bin,
        ["pack", ".", "--query", _QUERY, "--format", "json", *extra],
        cwd=ws.root,
        env=ws.env,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    assert isinstance(payload, dict)
    return payload


@pytest.mark.smoke
def test_index_json_builds_a_minimal_knowledge_graph(oc_bin, large_indexed_ws) -> None:
    """AC-005: `index --json` produces an index and a minimal knowledge graph."""
    report = index_workspace(oc_bin, large_indexed_ws)
    assert report.get("status") == "ok", report
    assert report.get("error") is None
    # 15 fixture modules + generated workspace files: both counters must be real.
    assert report.get("indexed_files", 0) >= 14, report
    assert report.get("symbol_count", 0) >= 20, report

    proc, _kg_status = run_json(
        oc_bin,
        ["knowledge-graph", "status", "--json"],
        cwd=large_indexed_ws.root,
        env=large_indexed_ws.env,
    )
    assert proc.returncode == 0, proc.stderr[:500]


@pytest.mark.smoke
def test_kg_search_finds_symbol_and_related_test(oc_bin, large_indexed_ws) -> None:
    """AC-006: `knowledge-graph search` finds a symbol and its related test."""
    proc, results = run_json(
        oc_bin,
        ["knowledge-graph", "search", "multiply_values", "--json"],
        cwd=large_indexed_ws.root,
        env=large_indexed_ws.env,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    assert isinstance(results, list) and results, "search must return matches"
    by_name = {r["name"]: r for r in results}
    assert "multiply_values" in by_name, f"symbol not found: {sorted(by_name)}"
    assert by_name["multiply_values"]["file_path"] == "calculator.py"
    assert "test_multiply_values" in by_name, (
        f"related test not found alongside the symbol: {sorted(by_name)}"
    )
    assert by_name["test_multiply_values"]["file_path"].startswith("tests/")


@pytest.mark.smoke
def test_pack_includes_relevant_and_excludes_irrelevant(oc_bin, large_indexed_ws) -> None:
    """AC-007: `pack` (JSON) includes relevant files and excludes irrelevant ones."""
    # A constrained budget forces a real inclusion/exclusion decision.
    payload = _pack(oc_bin, large_indexed_ws, "--max-tokens", "500")
    included = [item["source"] for item in payload["included"]]
    assert any("calculator.py" in source for source in included), (
        f"target module missing from pack: {included}"
    )
    assert any("test_calculator.py" in source for source in included), (
        f"related test missing from pack: {included}"
    )
    omitted = payload.get("omitted") or []
    omissions = payload.get("omissions") or []
    assert omitted or omissions, (
        "under a constrained budget some irrelevant content must be excluded"
    )
    # The distractor modules must never crowd out the target symbol.
    assert not any("calculator.py" in str(o.get("item_id", "")) for o in omissions), (
        f"the target module was sacrificed for irrelevant content: {omissions}"
    )


def test_pack_reports_token_budget(oc_bin, large_indexed_ws) -> None:
    """AC-008: `pack` reports its token budget and real usage."""
    payload = _pack(oc_bin, large_indexed_ws, "--max-tokens", "800")
    assert payload.get("available_tokens") == 800, payload.get("available_tokens")
    used = payload.get("used_tokens")
    assert isinstance(used, int) and 0 < used <= 800, (
        f"used_tokens must be a real count within budget, got {used}"
    )


@pytest.mark.xfail(
    reason="GAP-008: pack metrics block missing (no kg_nodes_used/kg_edges_used/"
    "memory_hits/protected_spans/compression_ratio in pack output)",
    strict=False,
)
def test_pack_reports_kg_usage_metrics(oc_bin, large_indexed_ws) -> None:
    """AC-008: `pack` reports KG usage metrics (mandatory pack metrics JSON)."""
    payload = _pack(oc_bin, large_indexed_ws, "--max-tokens", "800")
    context = payload.get("context") or payload
    for key in (
        "kg_nodes_used",
        "kg_edges_used",
        "memory_hits",
        "protected_spans",
        "protected_spans_kept",
        "compression_ratio",
    ):
        assert key in context, f"mandatory pack metric missing: {key}"


def test_incremental_index_updates_nodes_after_file_change(oc_bin, workspace) -> None:
    """AC-020: incremental KG indexing updates nodes after a file change."""
    ws = workspace("py_large_context")
    install_workspace(oc_bin, ws)
    index_workspace(oc_bin, ws)

    def search(symbol: str) -> list:
        proc, results = run_json(
            oc_bin,
            ["knowledge-graph", "search", symbol, "--json"],
            cwd=ws.root,
            env=ws.env,
        )
        assert proc.returncode == 0, proc.stderr[:400]
        return results

    # New file → new node.
    (ws.root / "widget_factory.py").write_text(
        "def brand_new_widget():\n    return 42\n", encoding="utf-8"
    )
    proc, report = run_json(
        oc_bin, ["index", ".", "--incremental", "--json"], cwd=ws.root, env=ws.env
    )
    assert proc.returncode == 0 and report.get("status") == "ok", report
    assert [r["name"] for r in search("brand_new_widget")] == ["brand_new_widget"]

    # Modified symbol → stale node removed (not duplicated), new node present.
    (ws.root / "widget_factory.py").write_text(
        "def renamed_widget_maker():\n    return 42\n", encoding="utf-8"
    )
    proc, report = run_json(
        oc_bin, ["index", ".", "--incremental", "--json"], cwd=ws.root, env=ws.env
    )
    assert proc.returncode == 0 and report.get("status") == "ok", report
    assert search("brand_new_widget") == [], "stale symbol must be removed from the KG"
    assert [r["name"] for r in search("renamed_widget_maker")] == ["renamed_widget_maker"]


def test_pack_under_token_pressure_keeps_protected_content(oc_bin, large_indexed_ws) -> None:
    """AC-021: under token pressure, `pack` stays in budget and keeps the target spans."""
    payload = _pack(oc_bin, large_indexed_ws, "--max-tokens", "500")
    used = payload.get("used_tokens")
    assert isinstance(used, int) and used <= 500, f"budget violated: {used} > 500"

    included_ids = [item["id"] for item in payload["included"]]
    # Protected-by-contract content: the target symbol and its test assertion
    # must survive pressure while distractors are dropped.
    assert any("calculator.py" in i and "multiply_values" in i for i in included_ids), (
        f"target symbol dropped under pressure: {included_ids}"
    )
    assert any("test_calculator.py" in i for i in included_ids), (
        f"related test assertion dropped under pressure: {included_ids}"
    )
    omissions = payload.get("omissions") or []
    assert omissions, "token pressure must produce recorded omissions"
    for omission in omissions:
        assert omission.get("reason"), f"omissions must be explained: {omission}"


def test_pack_under_pressure_reports_compression(oc_bin, large_indexed_ws) -> None:
    """AC-021: under token pressure, `pack` compresses and reports what it compressed."""
    payload = _pack(oc_bin, large_indexed_ws, "--max-tokens", "500")
    compression = payload.get("compression")
    assert compression, "pack under pressure must report a compression block"
    assert compression.get("enabled") is True, compression
    assert compression.get("items_compressed", 0) >= 1, compression
    assert compression["tokens_after"] <= compression["tokens_before"], (
        f"compression must not grow content: {compression}"
    )
