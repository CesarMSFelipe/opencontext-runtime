"""Behavior tests for the architecture analyzer (quality.architecture).

These are behavior tests over a REAL, tmp-isolated knowledge graph: every test
builds its own ``GraphDatabase`` under ``tmp_path/.storage/opencontext`` and feeds
``ArchitectureAnalyzer`` real Python source, so a regression in the graph passes
(Tarjan cycles, centrality fan-in roll-up, layer/boundary matching, tree-sitter
complexity) makes the assertion fail rather than silently pass.

Isolation guarantees (per the hard rules):

* The graph DB lives under ``tmp_path`` only.
* No test reads or writes the real ``~/.opencontext`` or the repo ``.opencontext``
  — ``ArchitectureAnalyzer`` is handed an explicit ``db_path`` under ``tmp_path``
  and never resolves a home/cwd config (asserted by :func:`test_no_real_dotdir`).
* The check path is deterministic and makes ZERO model calls — asserted by
  running ``analyze`` twice and comparing, and by stubbing the harness/LLM
  surfaces and confirming they are never reached.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from opencontext_core.indexing.graph_db import Edge, GraphDatabase, Node
from opencontext_core.indexing.scanner import ScannedFile
from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser
from opencontext_core.models.project import FileKind
from opencontext_core.quality.architecture import (
    ArchitectureAnalyzer,
    ArchitectureReport,
    BoundaryViolation,
    ComplexityFinding,
)
from opencontext_core.quality.ci_checks import CheckSeverity
from opencontext_core.quality.models import Finding, QualityMetrics
from opencontext_core.quality.rules import (
    ArchitectureRules,
    BoundaryRule,
    LayerRule,
)

_TREE_SITTER = TreeSitterParser()
requires_tree_sitter = pytest.mark.skipif(
    not (_TREE_SITTER.is_available() and "python" in _TREE_SITTER._languages),
    reason="tree-sitter python grammar not available",
)


# --------------------------------------------------------------------------- #
# Helpers / fixtures (all tmp_path-isolated)
# --------------------------------------------------------------------------- #


def _db_path(tmp_path: Path) -> Path:
    """The canonical graph DB path, under an isolated tmp ``.storage`` dir."""
    return tmp_path / ".storage" / "opencontext" / "context_graph.db"


def _scanned(relative_path: str, content: str, language: str = "python") -> ScannedFile:
    """A ScannedFile carrying real source content for a project-relative path."""
    return ScannedFile(
        path=Path(relative_path),
        relative_path=relative_path,
        language=language,
        file_type=FileKind.CODE,
        content=content,
        tokens=0,
        size_bytes=len(content.encode("utf-8")),
        summary="",
        metadata={},
    )


def _node(name: str, file_path: str, line: int = 1) -> Node:
    return Node(
        id=None,
        name=name,
        kind="function",
        file_path=file_path,
        line=line,
        column=0,
        end_line=line + 1,
        language="python",
        container=None,
        docstring=None,
        signature=f"def {name}()",
        is_exported=True,
    )


def _init_db(tmp_path: Path) -> Path:
    """Create an empty, schema-initialized graph DB under tmp_path. Returns its path."""
    db_path = _db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    db.close()
    return db_path


def _build_call_graph(tmp_path: Path, calls: list[tuple[str, str, str, str]]) -> Path:
    """Build a graph DB from ``(src_name, src_file, dst_name, dst_file)`` call edges.

    Each distinct ``(name, file)`` becomes one node; each tuple becomes one
    ``calls`` edge. Nodes are grouped and upserted per file in a SINGLE
    ``upsert_nodes`` call, because ``upsert_nodes`` prunes any node of that file
    not present in the batch — inserting one node at a time would leave only the
    last symbol per file. Returns the DB path under tmp_path.
    """
    db_path = _db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = GraphDatabase(db_path=db_path)
    db.init_schema()

    # Collect the distinct (name, file) symbols, grouped by file.
    by_file: dict[str, list[str]] = {}
    for src_name, src_file, dst_name, dst_file in calls:
        by_file.setdefault(src_file, [])
        by_file.setdefault(dst_file, [])
        if src_name not in by_file[src_file]:
            by_file[src_file].append(src_name)
        if dst_name not in by_file[dst_file]:
            by_file[dst_file].append(dst_name)

    # Upsert all of a file's symbols at once; map (name, file) -> stable id.
    ids: dict[tuple[str, str], str] = {}
    for file_path in sorted(by_file):
        names = by_file[file_path]
        nodes = [_node(name, file_path, line=i + 1) for i, name in enumerate(names)]
        node_ids = db.upsert_nodes(nodes)
        for name, node_id in zip(names, node_ids, strict=True):
            ids[(name, file_path)] = node_id

    for src_name, src_file, dst_name, dst_file in calls:
        db.insert_edge(
            Edge(
                id=None,
                source_node_id=ids[(src_name, src_file)],
                target_node_id=ids[(dst_name, dst_file)],
                kind="calls",
                call_site_file=src_file,
                call_site_line=1,
            )
        )
    db.close()
    return db_path


# A function whose cyclomatic complexity is independently known.
# base 1 + if + for + (and) + elif + while == 7.
_COMPLEX_SOURCE = (
    "def busy(x):\n"
    "    if x > 0:\n"
    "        for i in range(x):\n"
    "            if i % 2 == 0 and i > 2:\n"
    "                pass\n"
    "            elif i == 1:\n"
    "                pass\n"
    "    while x:\n"
    "        x -= 1\n"
    "    return x\n"
    "\n"
    "def simple(y):\n"
    "    return y + 1\n"
)


# --------------------------------------------------------------------------- #
# Cycles (file-level import SCC via DependencyGraphBuilder + Tarjan)
# --------------------------------------------------------------------------- #


def test_detect_cycles_flags_two_file_import_cycle(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", "from pkg.b import beta\n"),
        _scanned("pkg/b.py", "from pkg.a import alpha\n"),
        _scanned("pkg/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    cycles = analyzer.detect_cycles(ArchitectureRules())

    # Exactly one cycle, the {a,b} SCC, members sorted.
    assert cycles == (("pkg/a.py", "pkg/b.py"),)


def test_detect_cycles_none_when_imports_are_acyclic(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", "from pkg.b import beta\n"),
        _scanned("pkg/b.py", "x = 1\n"),  # b does not import a -> no cycle
        _scanned("pkg/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    assert analyzer.detect_cycles(ArchitectureRules()) == ()


def test_cycles_use_import_edges_not_call_edges(tmp_path: Path) -> None:
    """The headline cycle metric is the FILE-level import SCC, not call cycles.

    Here the persisted call graph has a 2-node call cycle, but the imports are
    acyclic. ``detect_cycles`` (imports) must report nothing; the call-cycle
    secondary signal must still see the call cycle — proving the two sources are
    distinct and import cycles do NOT come from the DB ``calls`` edges.
    """
    # Call cycle a<->b in the DB.
    db_path = _build_call_graph(
        tmp_path,
        [
            ("a", "src/a.py", "b", "src/b.py"),
            ("b", "src/b.py", "a", "src/a.py"),
        ],
    )
    # Imports are acyclic (a imports b only).
    files = [
        _scanned("src/a.py", "from src.b import b\n"),
        _scanned("src/b.py", "x = 1\n"),
        _scanned("src/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)

    assert analyzer.detect_cycles(ArchitectureRules()) == ()  # import cycles: none
    call_cycles = analyzer.detect_call_cycles()  # secondary signal: the call cycle
    assert len(call_cycles) == 1
    assert len(call_cycles[0]) == 2


def test_cycles_skipped_when_no_source_scanned(tmp_path: Path) -> None:
    """Import cycles need source; with ``scanned_files=None`` they degrade honestly.

    The pass returns no cycles AND ``analyze`` records a skipped reason — never a
    silent clean.
    """
    db_path = _init_db(tmp_path)
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=None)

    assert analyzer.detect_cycles(ArchitectureRules()) == ()
    report = analyzer.analyze(ArchitectureRules())
    assert any(reason.startswith("max_cycles") for reason in report.skipped)


# --------------------------------------------------------------------------- #
# God files (centrality fan-in roll-up + LOC)
# --------------------------------------------------------------------------- #


def test_detect_god_files_by_fan_in(tmp_path: Path) -> None:
    # core.py defines one symbol called by 10 callers in callers.py -> fan-in 10.
    calls = [(f"c{i}", "src/callers.py", "core", "src/core.py") for i in range(10)]
    db_path = _build_call_graph(tmp_path, calls)

    analyzer = ArchitectureAnalyzer(db_path)
    gods = analyzer.detect_god_files(ArchitectureRules(god_file_in_degree=8))

    god_files = {g.file: g for g in gods}
    assert "src/core.py" in god_files
    assert god_files["src/core.py"].in_degree == 10
    # The callers file has zero fan-in -> not a god file.
    assert "src/callers.py" not in god_files


def test_detect_god_files_by_loc(tmp_path: Path) -> None:
    """A file under the fan-in cap but over the LOC cap is still a god file."""
    db_path = _init_db(tmp_path)
    big = "\n".join(f"x{i} = {i}" for i in range(50)) + "\n"  # ~50 lines of code
    expected_loc = big.count("\n") + 1  # analyzer's LOC convention
    files = [_scanned("src/big.py", big)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)

    gods = analyzer.detect_god_files(ArchitectureRules(god_file_in_degree=999, god_file_loc=40))
    god_files = {g.file: g for g in gods}
    assert "src/big.py" in god_files
    # LOC is over the 40-line cap (the size signal); fan-in is 0 (under the cap).
    assert god_files["src/big.py"].loc == expected_loc
    assert god_files["src/big.py"].loc > 40
    assert god_files["src/big.py"].in_degree == 0


def test_detect_god_files_disabled_when_flag_off(tmp_path: Path) -> None:
    calls = [(f"c{i}", "src/callers.py", "core", "src/core.py") for i in range(10)]
    db_path = _build_call_graph(tmp_path, calls)
    analyzer = ArchitectureAnalyzer(db_path)

    assert analyzer.detect_god_files(ArchitectureRules(no_god_files=False)) == ()


# --------------------------------------------------------------------------- #
# Boundaries (layer glob match + directed deny rule)
# --------------------------------------------------------------------------- #


def test_detect_boundaries_flags_disallowed_dependency(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    files = [
        # domain importing infra is the forbidden direction.
        _scanned("domain/user.py", "from infra.db import save\n"),
        _scanned("infra/db.py", "def save():\n    return 1\n"),
        _scanned("domain/__init__.py", ""),
        _scanned("infra/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)

    layers = (
        LayerRule(name="domain", paths=("domain/*",), order=0),
        LayerRule(name="infra", paths=("infra/*",), order=1),
    )
    boundaries = (
        BoundaryRule(from_layer="domain", to_layer="infra", allow=False, reason="keep domain pure"),
    )
    violations = analyzer.detect_boundaries(layers, boundaries)

    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, BoundaryViolation)
    assert v.source_file == "domain/user.py"
    assert v.target_file == "infra/db.py"
    assert v.from_layer == "domain"
    assert v.to_layer == "infra"
    assert v.reason == "keep domain pure"


def test_detect_boundaries_allowed_direction_is_clean(tmp_path: Path) -> None:
    """The reverse (allowed) direction must NOT be a violation."""
    db_path = _init_db(tmp_path)
    files = [
        # infra importing domain is allowed (only domain->infra is denied).
        _scanned("infra/db.py", "from domain.user import User\n"),
        _scanned("domain/user.py", "class User:\n    pass\n"),
        _scanned("domain/__init__.py", ""),
        _scanned("infra/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    layers = (
        LayerRule(name="domain", paths=("domain/*",)),
        LayerRule(name="infra", paths=("infra/*",)),
    )
    boundaries = (BoundaryRule(from_layer="domain", to_layer="infra", allow=False),)

    assert analyzer.detect_boundaries(layers, boundaries) == ()


def test_detect_boundaries_noop_without_rules(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    files = [
        _scanned("domain/user.py", "from infra.db import save\n"),
        _scanned("infra/db.py", "def save():\n    return 1\n"),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    # No layers / no boundaries declared -> teams opt in, so it is a no-op.
    assert analyzer.detect_boundaries((), ()) == ()


# --------------------------------------------------------------------------- #
# Complexity (tree-sitter cyclomatic) — requires the python grammar
# --------------------------------------------------------------------------- #


@requires_tree_sitter
def test_compute_complexity_flags_over_threshold(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    files = [_scanned("pkg/c.py", _COMPLEX_SOURCE)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)

    findings = analyzer.compute_complexity(ArchitectureRules(max_cc=3))
    by_symbol = {f.symbol: f for f in findings}

    # 'busy' has cc 7 (> 3) and is flagged; 'simple' has cc 1 and is not.
    assert "busy" in by_symbol
    assert isinstance(by_symbol["busy"], ComplexityFinding)
    assert by_symbol["busy"].complexity == 7
    assert by_symbol["busy"].file == "pkg/c.py"
    assert "simple" not in by_symbol


@requires_tree_sitter
def test_compute_complexity_clean_when_under_threshold(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    files = [_scanned("pkg/c.py", _COMPLEX_SOURCE)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    # max_cc=25 is above 'busy' (7) -> nothing flagged.
    assert analyzer.compute_complexity(ArchitectureRules(max_cc=25)) == ()


def test_complexity_skipped_when_tree_sitter_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When tree-sitter is unavailable, complexity is recorded as skipped, never clean.

    The parser is stubbed to report unavailable so the test is meaningful even on
    a CI box that *does* have tree-sitter installed.
    """
    db_path = _init_db(tmp_path)
    files = [_scanned("pkg/c.py", _COMPLEX_SOURCE)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    monkeypatch.setattr(analyzer._parser, "is_available", lambda: False)

    assert analyzer.compute_complexity(ArchitectureRules(max_cc=1)) == ()
    report = analyzer.analyze(ArchitectureRules(max_cc=1))
    assert any(reason.startswith("max_cc") for reason in report.skipped)


# --------------------------------------------------------------------------- #
# Coupling grade
# --------------------------------------------------------------------------- #


def test_coupling_grade_clean_graph_is_a(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)  # empty graph -> worst fan-in 0 -> grade A
    analyzer = ArchitectureAnalyzer(db_path)
    assert analyzer.coupling_grade() == "A"


def test_coupling_grade_worsens_with_fan_in(tmp_path: Path) -> None:
    # core called by 10 distinct symbols -> worst in-degree 10 -> band 'C'.
    calls = [(f"c{i}", f"src/c{i}.py", "core", "src/core.py") for i in range(10)]
    db_path = _build_call_graph(tmp_path, calls)
    analyzer = ArchitectureAnalyzer(db_path)
    assert analyzer.coupling_grade() == "C"


# --------------------------------------------------------------------------- #
# Full analyze() orchestration + metrics + Finding normalization
# --------------------------------------------------------------------------- #


@requires_tree_sitter
def test_analyze_normalizes_every_pass_into_findings(tmp_path: Path) -> None:
    """One pass that exercises cycles + god-file + complexity together.

    Asserts the report carries each typed result AND a corresponding normalized
    ``Finding(category='architecture')`` with the right rule id and severity.
    """
    db_path = _init_db(tmp_path)
    # An import cycle (a<->b) plus a complex function in c.py.
    files = [
        _scanned("pkg/a.py", "from pkg.b import beta\n"),
        _scanned("pkg/b.py", "from pkg.a import alpha\n"),
        _scanned("pkg/c.py", _COMPLEX_SOURCE),
        _scanned("pkg/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules(max_cc=3, god_file_loc=5))

    assert isinstance(report, ArchitectureReport)
    rules_present = {f.rule for f in report.findings}
    assert "max_cycles" in rules_present
    assert "max_cc" in rules_present

    # Every finding is in the architecture category and carries a severity.
    for f in report.findings:
        assert isinstance(f, Finding)
        assert f.category == "architecture"
        assert isinstance(f.severity, CheckSeverity)

    # The cycle finding is an error; the complexity finding is a warning.
    sev_by_rule = {f.rule: f.severity for f in report.findings}
    assert sev_by_rule["max_cycles"] == CheckSeverity.ERROR
    assert sev_by_rule["max_cc"] == CheckSeverity.WARNING


def test_analyze_metrics_reflect_graph(tmp_path: Path) -> None:
    db_path = _build_call_graph(
        tmp_path,
        [(f"c{i}", f"src/c{i}.py", "core", "src/core.py") for i in range(10)],
    )
    files = [
        _scanned("src/a.py", "from src.b import b\n"),
        _scanned("src/b.py", "from src.a import a\n"),  # import cycle
        _scanned("src/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules())
    m = report.metrics

    assert isinstance(m, QualityMetrics)
    assert m.cycles == 1  # one import SCC
    assert m.max_in_degree == 10  # core's fan-in
    assert m.node_count == 11  # core + 10 callers
    assert m.edge_count == 10


def test_no_god_files_threshold_respected(tmp_path: Path) -> None:
    """Below the configured fan-in cap, a file is NOT a god file (metric == 0)."""
    calls = [(f"c{i}", f"src/c{i}.py", "core", "src/core.py") for i in range(3)]
    db_path = _build_call_graph(tmp_path, calls)
    analyzer = ArchitectureAnalyzer(db_path)
    # fan-in 3 < cap 8 -> not flagged.
    report = analyzer.analyze(ArchitectureRules(god_file_in_degree=8))
    assert report.metrics.god_files == 0
    assert all(f.rule != "no_god_files" for f in report.findings)


# --------------------------------------------------------------------------- #
# Scope filtering (changed_files)
# --------------------------------------------------------------------------- #


@requires_tree_sitter
def test_analyze_scope_filters_symbol_findings(tmp_path: Path) -> None:
    """With ``changed_files`` given, only in-scope complexity findings are reported."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/c.py", _COMPLEX_SOURCE),  # has the complex 'busy'
        _scanned("pkg/d.py", _COMPLEX_SOURCE),  # also complex, but out of scope
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)

    report = analyzer.analyze(ArchitectureRules(max_cc=3), changed_files=["pkg/c.py"])
    cc_files = {f.file for f in report.findings if f.rule == "max_cc"}
    assert cc_files == {"pkg/c.py"}  # d.py is filtered out of scope


def test_analyze_cycle_reported_only_when_member_in_scope(tmp_path: Path) -> None:
    """A whole-graph cycle is only *reported* when a changed file participates."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", "from pkg.b import beta\n"),
        _scanned("pkg/b.py", "from pkg.a import alpha\n"),
        _scanned("pkg/unrelated.py", "x = 1\n"),
        _scanned("pkg/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)

    # Scope is a file NOT in the cycle -> the cycle is not surfaced as a finding.
    out_of_scope = analyzer.analyze(ArchitectureRules(), changed_files=["pkg/unrelated.py"])
    assert all(f.rule != "max_cycles" for f in out_of_scope.findings)

    # Scope includes a cycle member -> it IS surfaced.
    in_scope = analyzer.analyze(ArchitectureRules(), changed_files=["pkg/a.py"])
    assert any(f.rule == "max_cycles" for f in in_scope.findings)


# --------------------------------------------------------------------------- #
# Determinism + zero model calls + isolation guarantees
# --------------------------------------------------------------------------- #


@requires_tree_sitter
def test_analyze_is_deterministic(tmp_path: Path) -> None:
    """Identical graph content -> identical report (no float drift, sorted output)."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", "from pkg.b import beta\n"),
        _scanned("pkg/b.py", "from pkg.a import alpha\n"),
        _scanned("pkg/c.py", _COMPLEX_SOURCE),
        _scanned("pkg/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    rules = ArchitectureRules(max_cc=3)

    first = analyzer.analyze(rules)
    second = analyzer.analyze(rules)

    assert first.cycles == second.cycles
    assert first.god_files == second.god_files
    assert first.complexity == second.complexity
    assert first.metrics == second.metrics
    # Findings compare equal field-by-field (frozen dataclasses).
    assert first.findings == second.findings


def test_analyze_makes_zero_model_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole architecture pass must touch no LLM/sampling surface.

    We poison any import of a model client module: if the analyzer tried to load
    one, the import machinery would raise. This guards the 'deterministic, zero
    model calls' contract at the import boundary.
    """
    import builtins

    real_import = builtins.__import__
    forbidden = ("anthropic", "openai", "ollama")

    def guarded_import(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if any(name == f or name.startswith(f + ".") for f in forbidden):
            raise AssertionError(f"architecture pass attempted to import a model client: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", "from pkg.b import beta\n"),
        _scanned("pkg/b.py", "from pkg.a import alpha\n"),
        _scanned("pkg/__init__.py", ""),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules())
    # Sanity: it still produced a real result under the guard.
    assert report.metrics.cycles == 1


def test_no_real_dotdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The analyzer must read only the explicit tmp DB, never ~/.opencontext or repo.

    We point HOME at an empty tmp dir and assert that directory is never created
    or read, and that the analyzer operates purely off the db_path it was handed.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    db_path = _init_db(tmp_path)
    files = [_scanned("pkg/a.py", "x = 1\n")]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    analyzer.analyze(ArchitectureRules())

    # No ~/.opencontext was touched by the architecture pass.
    assert not (fake_home / ".opencontext").exists()


def test_missing_db_degrades_without_raising(tmp_path: Path) -> None:
    """A non-existent DB path must not crash the god-file roll-up (degrade honestly).

    With no DB on disk the node->file map is empty, so god-file detection falls
    back to LOC-only rather than raising a sqlite error.
    """
    db_path = _db_path(tmp_path)  # parent not created, DB absent
    big = "\n".join(f"x{i} = {i}" for i in range(50)) + "\n"
    files = [_scanned("src/big.py", big)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)

    gods = analyzer.detect_god_files(ArchitectureRules(god_file_in_degree=999, god_file_loc=40))
    assert {g.file for g in gods} == {"src/big.py"}


def test_db_path_stays_under_tmp(tmp_path: Path) -> None:
    """Guard the isolation invariant: the DB the analyzer uses is under tmp_path."""
    db_path = _init_db(tmp_path)
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=[_scanned("a.py", "x=1\n")])
    analyzer.analyze(ArchitectureRules())

    assert str(analyzer.db_path).startswith(str(tmp_path))
    # The only DB created sits inside the isolated tmp tree.
    created = list(tmp_path.rglob("context_graph.db"))
    assert created == [db_path]


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    sys.exit(pytest.main([__file__, "-q"]))


@pytest.mark.parametrize(
    "values,expected",
    [
        ([], 0),
        ([100], 0),  # a single file: no distribution signal
        ([0, 0], 0),  # all empty: no signal
        ([10, 10, 10, 10], 0),  # perfectly even -> 0
    ],
)
def test_gini_bp_degenerate_and_even(values: list[int], expected: int) -> None:
    from opencontext_core.quality.architecture import _gini_bp

    assert _gini_bp(values) == expected


def test_gini_bp_rises_with_concentration() -> None:
    from opencontext_core.quality.architecture import _gini_bp

    even = _gini_bp([50, 50, 50, 50])
    mild = _gini_bp([10, 20, 30, 100])
    extreme = _gini_bp([1, 1, 1, 1000])
    assert even == 0
    assert 0 < mild < extreme <= 10000
