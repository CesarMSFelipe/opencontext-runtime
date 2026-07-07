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
    """AC-006: `knowledge-graph search` finds a symbol and its related test,
    and `impact --json` reports the symbol's blast radius as pure JSON (DOD2-4:
    the KG finds symbols, tests AND impact through the real CLI)."""
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

    # Impact leg (DOD2-4): run_json enforces the JSON purity rule, so any
    # human-facing header mixed into stdout fails here.
    proc, impacted = run_json(
        oc_bin,
        ["knowledge-graph", "impact", "multiply_values", "--json"],
        cwd=large_indexed_ws.root,
        env=large_indexed_ws.env,
    )
    assert proc.returncode == 0, proc.stderr[:500]
    assert isinstance(impacted, list) and impacted, "impact must report affected symbols"
    impacted_names = {r["name"] for r in impacted}
    assert "test_multiply_values" in impacted_names, (
        f"changing multiply_values must impact its test: {sorted(impacted_names)}"
    )


#: The 12 "deliberately unrelated" distractor modules seeded in py_large_context.
_DISTRACTOR_MODULES = (
    "aquarium_sensors.py",
    "chess_engine.py",
    "fitness_tracker.py",
    "garden_planner.py",
    "holiday_scheduler.py",
    "invoice_ledger.py",
    "library_catalog.py",
    "music_playlist.py",
    "recipe_book.py",
    "rocket_telemetry.py",
    "traffic_monitor.py",
    "weather_report.py",
)

#: Omission reasons that mean content was SACRIFICED to the budget (as opposed
#: to a redundant whole-file skipped because its spans are already included).
_SACRIFICE_REASONS = {
    "required_priority_budget_exhausted",
    "token_budget_exceeded",
    "item_exceeds_available_budget",
}


@pytest.mark.smoke
def test_pack_includes_relevant_and_excludes_irrelevant(oc_bin, large_indexed_ws) -> None:
    """AC-007: `pack` (JSON) includes relevant files and excludes irrelevant ones,
    meeting the §29.2 numeric targets on the large fixture (MET-TOKENS:
    relevant-file inclusion >= 95%, irrelevant-file exclusion >= 80%)."""
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
    # The distractor modules must never crowd out the target symbol: no
    # calculator content may be sacrificed to the budget while distractors ride.
    assert not any(
        "calculator.py" in str(o.get("item_id", "")) and o.get("reason") in _SACRIFICE_REASONS
        for o in omissions
    ), f"the target module was sacrificed for irrelevant content: {omissions}"

    # §29.2 numeric targets, computed per FILE (any included span counts as
    # that file being included).
    included_files = {source.split(":")[0] for source in included}
    relevant = ("calculator.py", "tests/test_calculator.py")
    inclusion_rate = sum(1 for f in relevant if f in included_files) / len(relevant)
    assert inclusion_rate >= 0.95, (
        f"relevant file inclusion {inclusion_rate:.0%} < 95%: {sorted(included_files)}"
    )
    excluded = [d for d in _DISTRACTOR_MODULES if d not in included_files]
    exclusion_rate = len(excluded) / len(_DISTRACTOR_MODULES)
    assert exclusion_rate >= 0.80, (
        f"irrelevant file exclusion {exclusion_rate:.0%} < 80%: "
        f"included distractors = {sorted(set(_DISTRACTOR_MODULES) - set(excluded))}"
    )


def test_pack_reports_token_budget(oc_bin, large_indexed_ws) -> None:
    """AC-008: `pack` reports its token budget and real usage."""
    payload = _pack(oc_bin, large_indexed_ws, "--max-tokens", "800")
    assert payload.get("available_tokens") == 800, payload.get("available_tokens")
    used = payload.get("used_tokens")
    assert isinstance(used, int) and 0 < used <= 800, (
        f"used_tokens must be a real count within budget, got {used}"
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

    # §29.2 numeric targets in the pack payload itself (MET-TOKENS).
    context = payload.get("context") or {}
    assert context.get("protected_spans", 0) > 0, context
    assert context.get("protected_spans_kept") == context.get("protected_spans"), (
        f"protected spans kept must be 100%: {context.get('protected_spans_kept')}"
        f"/{context.get('protected_spans')}"
    )
    input_estimate = context.get("input_tokens_estimated")
    output_estimate = context.get("output_tokens_estimated")
    assert isinstance(input_estimate, int) and input_estimate > 0, context
    assert isinstance(output_estimate, int), context
    reduction = 1 - (output_estimate / input_estimate)
    assert reduction >= 0.40, (
        f"token reduction under budget was {reduction:.0%} (< 40%): "
        f"{output_estimate}/{input_estimate} tokens"
    )


def test_pack_under_pressure_reports_compression(oc_bin, large_indexed_ws) -> None:
    """AC-021: under token pressure, `pack` compresses and reports what it compressed.

    The 200-token budget is tighter than the relevant spans alone (~200 tokens),
    so fitting them forces real dynamic compression even now that low-relevance
    whole files are excluded up front (full_file_threshold)."""
    payload = _pack(oc_bin, large_indexed_ws, "--max-tokens", "200")
    compression = payload.get("compression")
    assert compression, "pack under pressure must report a compression block"
    assert compression.get("enabled") is True, compression
    assert compression.get("items_compressed", 0) >= 1, compression
    assert compression["tokens_after"] <= compression["tokens_before"], (
        f"compression must not grow content: {compression}"
    )
