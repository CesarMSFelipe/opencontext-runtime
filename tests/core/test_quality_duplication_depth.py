"""Behavior tests for the Phase-3 architecture passes: duplication + code-nesting.

These exercise :meth:`ArchitectureAnalyzer._compute_duplication` (the in-process,
model-free clone detector) and :meth:`ArchitectureAnalyzer._compute_nesting` (the
code block-nesting depth pass), plus the ``no_duplication`` / ``max_nesting``
:class:`Finding` objects they produce and the two new :class:`QualityMetrics`
fields (``duplication`` / ``max_nesting``) they feed.

Isolation guarantees (per the hard rules):

* Every analyzer is handed an explicit ``db_path`` under ``tmp_path`` and a real
  :class:`ScannedFile` source — no home/cwd config is ever read.
* The check path is deterministic and makes ZERO model calls / ZERO subprocesses
  — asserted by running ``analyze`` twice and comparing, and by the fact the
  passes only call the in-process tree-sitter parser + stdlib string hashing.
* tree-sitter cases are skipped (not silently passed) when the python grammar is
  unavailable; the degrade path is asserted to record a skip-reason, not a clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.indexing.scanner import ScannedFile
from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser
from opencontext_core.models.project import FileKind
from opencontext_core.quality.architecture import (
    ArchitectureAnalyzer,
    DuplicationFinding,
    NestingFinding,
)
from opencontext_core.quality.ci_checks import CheckSeverity
from opencontext_core.quality.models import QualityMetrics, finding_key
from opencontext_core.quality.rules import ArchitectureRules

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


def _init_db(tmp_path: Path) -> Path:
    """Create an empty, schema-initialized graph DB under tmp_path. Returns its path."""
    db_path = _db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = GraphDatabase(db_path=db_path)
    db.init_schema()
    db.close()
    return db_path


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


# A substantial function body (well over the default 40-token min) so it is a
# real clone candidate, not boilerplate. Two copies of this in different files
# should be flagged as ONE duplication pair.
_CLONE_BODY = (
    "def process_records(records, threshold, label):\n"
    "    total = 0\n"
    "    accepted = []\n"
    "    rejected = []\n"
    "    for record in records:\n"
    "        value = record.get('value', 0)\n"
    "        if value > threshold:\n"
    "            accepted.append((label, record, value))\n"
    "            total = total + value\n"
    "        else:\n"
    "            rejected.append((label, record))\n"
    "    summary = {'total': total, 'accepted': len(accepted)}\n"
    "    return accepted, rejected, summary\n"
)

# The SAME body, only reformatted (extra blank lines, different indentation
# width, trailing spaces). The deterministic whitespace normalizer must still
# treat it as a clone of ``_CLONE_BODY``.
_CLONE_BODY_REFORMATTED = (
    "def process_records(records, threshold, label):\n"
    "\n"
    "      total = 0\n"
    "      accepted = []\n"
    "\n"
    "      rejected = []\n"
    "      for record in records:\n"
    "          value = record.get('value', 0)\n"
    "          if value > threshold:\n"
    "              accepted.append((label, record, value))\n"
    "              total = total + value\n"
    "          else:\n"
    "              rejected.append((label, record))\n"
    "      summary = {'total': total, 'accepted': len(accepted)}\n"
    "      return accepted, rejected, summary\n"
)

# A tiny function: far below min_duplicate_tokens. Two copies must NOT be flagged.
_TINY_BODY = "def gx():\n    return 1\n"
_TINY_BODY_2 = "def gy():\n    return 1\n"

# A genuinely different, substantial function — must not clone-match _CLONE_BODY,
# yet itself large enough (>= min_duplicate_tokens shingles) to be a clone
# candidate when paired with its OWN copy.
_DIFFERENT_BODY = (
    "def render_report(rows, title, footer, separator, indent):\n"
    "    lines = [title, separator]\n"
    "    width = 0\n"
    "    seen = set()\n"
    "    for row in rows:\n"
    "        name = str(row.get('name', 'anonymous'))\n"
    "        count = int(row.get('count', 0))\n"
    "        width = max(width, len(name))\n"
    "        seen.add(name)\n"
    "        lines.append(indent + name + ': ' + str(count))\n"
    "    lines.append(separator)\n"
    "    lines.append(footer)\n"
    "    lines.append('=' * width)\n"
    "    return '\\n'.join(lines), len(seen), width\n"
)


# --------------------------------------------------------------------------- #
# Duplication: _compute_duplication + the 'no_duplication' Finding
# --------------------------------------------------------------------------- #


@requires_tree_sitter
def test_identical_functions_in_two_files_flagged_once(tmp_path: Path) -> None:
    """Two byte-identical functions in different files -> exactly ONE pair."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", _CLONE_BODY),
        _scanned("pkg/b.py", _CLONE_BODY),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules())

    dups = report.duplication
    assert len(dups) == 1, dups
    dup = dups[0]
    assert isinstance(dup, DuplicationFinding)
    # Pair ordered canonically by (file, symbol).
    assert (dup.file_a, dup.symbol_a) <= (dup.file_b, dup.symbol_b)
    assert dup.file_a == "pkg/a.py"
    assert dup.file_b == "pkg/b.py"
    assert dup.symbol_a == "process_records"
    assert dup.symbol_b == "process_records"
    assert dup.tokens > 0

    # A 'no_duplication' Finding is emitted for the pair.
    dup_findings = [f for f in report.findings if f.rule == "no_duplication"]
    assert len(dup_findings) == 1
    f = dup_findings[0]
    assert f.severity is CheckSeverity.WARNING
    assert f.category == "architecture"
    assert f.file == "pkg/a.py"
    assert "process_records" in f.message
    assert f.metadata["file_b"] == "pkg/b.py"
    assert f.metadata["symbol_b"] == "process_records"
    assert f.metadata["tokens"] == dup.tokens


@requires_tree_sitter
def test_whitespace_only_difference_is_still_a_clone(tmp_path: Path) -> None:
    """Normalization: bodies differing only in formatting are still flagged."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", _CLONE_BODY),
        _scanned("pkg/b.py", _CLONE_BODY_REFORMATTED),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules())

    assert len(report.duplication) == 1, report.duplication
    assert report.metrics.duplication == 1


@requires_tree_sitter
def test_function_below_min_tokens_not_flagged(tmp_path: Path) -> None:
    """A function smaller than ``min_duplicate_tokens`` is never a clone."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", _TINY_BODY),
        _scanned("pkg/b.py", _TINY_BODY),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules())

    assert report.duplication == ()
    assert report.metrics.duplication == 0
    assert not [f for f in report.findings if f.rule == "no_duplication"]


@requires_tree_sitter
def test_trivially_different_bodies_not_flagged(tmp_path: Path) -> None:
    """Two substantial but genuinely different functions are not clones."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", _CLONE_BODY),
        _scanned("pkg/b.py", _DIFFERENT_BODY),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules())

    assert report.duplication == ()
    assert report.metrics.duplication == 0


@requires_tree_sitter
def test_two_distinct_clone_pairs_have_distinct_finding_keys(tmp_path: Path) -> None:
    """The composite pair symbol makes finding_key UNIQUE per distinct pair.

    Guards the cycle-fingerprint-style collision risk: without a per-pair
    composite ``symbol`` every dup hashes to one key and the ratchet masks new
    clones. Two independent clone pairs must yield two distinct keys.
    """
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", _CLONE_BODY),
        _scanned("pkg/b.py", _CLONE_BODY),
        _scanned("pkg/c.py", _DIFFERENT_BODY),
        _scanned("pkg/d.py", _DIFFERENT_BODY),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules())

    dup_findings = [f for f in report.findings if f.rule == "no_duplication"]
    assert len(dup_findings) == 2, dup_findings

    keys = {finding_key(f.rule, f.file, f.symbol) for f in dup_findings}
    assert len(keys) == 2, "distinct clone pairs collapsed to one ratchet key"
    # And the symbols themselves are distinct, canonical pair fingerprints.
    symbols = {f.symbol for f in dup_findings}
    assert len(symbols) == 2
    assert all(s and s.startswith("dup:") for s in symbols)


@requires_tree_sitter
def test_duplication_reported_when_either_site_in_scope(tmp_path: Path) -> None:
    """Cross-file signal: a pair is reported when EITHER site is in scope."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", _CLONE_BODY),
        _scanned("pkg/b.py", _CLONE_BODY),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)

    # Only b.py changed; the pair must still surface (its partner a.py is the
    # other site). Mirrors the cycle "any member in scope" rule.
    report = analyzer.analyze(ArchitectureRules(), changed_files=["pkg/b.py"])
    assert len(report.duplication) == 1, report.duplication

    # A scope touching NEITHER site reports nothing.
    fresh = ArchitectureAnalyzer(db_path, scanned_files=files)
    report_none = fresh.analyze(ArchitectureRules(), changed_files=["pkg/unrelated.py"])
    assert report_none.duplication == ()


@requires_tree_sitter
def test_duplication_is_deterministic(tmp_path: Path) -> None:
    """analyze() twice -> identical duplication findings (no set-order leak)."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", _CLONE_BODY),
        _scanned("pkg/b.py", _CLONE_BODY),
        _scanned("pkg/c.py", _CLONE_BODY),
    ]
    first = ArchitectureAnalyzer(db_path, scanned_files=files).analyze(ArchitectureRules())
    second = ArchitectureAnalyzer(db_path, scanned_files=files).analyze(ArchitectureRules())
    assert first.duplication == second.duplication
    dup_keys_1 = [(f.rule, f.file, f.symbol) for f in first.findings if f.rule == "no_duplication"]
    dup_keys_2 = [(f.rule, f.file, f.symbol) for f in second.findings if f.rule == "no_duplication"]
    assert dup_keys_1 == dup_keys_2


def test_duplication_skipped_when_tree_sitter_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Degrade honestly: no parser -> skip-reason recorded, NO finding."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", _CLONE_BODY),
        _scanned("pkg/b.py", _CLONE_BODY),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    monkeypatch.setattr(analyzer._parser, "is_available", lambda: False)

    report = analyzer.analyze(ArchitectureRules())
    assert report.duplication == ()
    assert "no_duplication:tree-sitter-unavailable" in report.skipped
    assert not [f for f in report.findings if f.rule == "no_duplication"]


def test_duplication_no_scanned_files_returns_empty(tmp_path: Path) -> None:
    """Zero scanned files -> empty duplication, no crash."""
    db_path = _init_db(tmp_path)
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=[])
    report = analyzer.analyze(ArchitectureRules())
    assert report.duplication == ()
    assert report.metrics.duplication == 0


# --------------------------------------------------------------------------- #
# Nesting: _compute_nesting + max_nesting_depth + the 'max_nesting' Finding
# --------------------------------------------------------------------------- #


# A function nested 4 blocks deep (if -> for -> if -> while). Default ceiling is
# rules.max_nesting == 5, so at max_nesting=3 it is flagged.
_DEEP_SOURCE = (
    "def deep(items):\n"
    "    if items:\n"
    "        for it in items:\n"
    "            if it:\n"
    "                while it.ready:\n"
    "                    it.step()\n"
    "    return items\n"
)

_SHALLOW_SOURCE = "def shallow(x):\n    if x:\n        return x\n    return 0\n"


@requires_tree_sitter
def test_function_deeper_than_threshold_flagged(tmp_path: Path) -> None:
    """A function nested past ``rules.max_nesting`` is flagged with its depth."""
    db_path = _init_db(tmp_path)
    files = [_scanned("pkg/a.py", _DEEP_SOURCE)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    rules = ArchitectureRules(max_nesting=3)
    report = analyzer.analyze(rules)

    nests = report.nesting
    assert len(nests) == 1, nests
    n = nests[0]
    assert isinstance(n, NestingFinding)
    assert n.file == "pkg/a.py"
    assert n.symbol == "deep"
    assert n.depth == 4  # if/for/if/while
    assert report.metrics.max_nesting == 4

    nest_findings = [f for f in report.findings if f.rule == "max_nesting"]
    assert len(nest_findings) == 1
    f = nest_findings[0]
    assert f.severity is CheckSeverity.WARNING
    assert f.symbol == "deep"
    assert f.metadata["depth"] == 4
    assert "4" in f.message


@requires_tree_sitter
def test_shallow_function_not_flagged(tmp_path: Path) -> None:
    """A function at/under the ceiling is not flagged (depth is exclusive cap)."""
    db_path = _init_db(tmp_path)
    files = [_scanned("pkg/a.py", _SHALLOW_SOURCE)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules(max_nesting=3))
    assert report.nesting == ()
    assert not [f for f in report.findings if f.rule == "max_nesting"]
    # Like max_cc, the metric reflects only OVER-threshold rows -> 0 here.
    assert report.metrics.max_nesting == 0


@requires_tree_sitter
def test_nested_inner_function_reported_on_its_own_row(tmp_path: Path) -> None:
    """A nested inner function's depth is its OWN row, not folded into the outer.

    Mirrors cyclomatic_complexity's nested-function skip: the inner function's
    blocks must not inflate the enclosing function's nesting.
    """
    src = (
        "def outer(items):\n"
        "    if items:\n"
        "        def inner(z):\n"
        "            if z:\n"
        "                for w in z:\n"
        "                    if w:\n"
        "                        return w\n"
        "            return None\n"
        "        return inner\n"
        "    return None\n"
    )
    db_path = _init_db(tmp_path)
    files = [_scanned("pkg/a.py", src)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules(max_nesting=0))

    by_symbol = {n.symbol: n.depth for n in report.nesting}
    assert "outer" in by_symbol and "inner" in by_symbol
    # ``outer`` only has its own ``if`` (1) — the inner def's blocks are excluded.
    assert by_symbol["outer"] == 1
    # ``inner`` measured independently: if/for/if == 3.
    assert by_symbol["inner"] == 3


@requires_tree_sitter
def test_max_nesting_zero_disables_findings_but_not_metric(tmp_path: Path) -> None:
    """``max_nesting=0`` disables the FINDING; the metric still reports depth."""
    db_path = _init_db(tmp_path)
    files = [_scanned("pkg/a.py", _DEEP_SOURCE)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules(max_nesting=0))
    assert not [f for f in report.findings if f.rule == "max_nesting"]


@requires_tree_sitter
def test_nesting_finding_key_stable_across_line_shift(tmp_path: Path) -> None:
    """Symbol-scoped key is stable when the function moves down by blank lines."""
    db_path = _init_db(tmp_path)
    a = ArchitectureAnalyzer(db_path, scanned_files=[_scanned("pkg/a.py", _DEEP_SOURCE)]).analyze(
        ArchitectureRules(max_nesting=3)
    )
    shifted = "\n\n\n" + _DEEP_SOURCE
    b = ArchitectureAnalyzer(db_path, scanned_files=[_scanned("pkg/a.py", shifted)]).analyze(
        ArchitectureRules(max_nesting=3)
    )

    fa = next(f for f in a.findings if f.rule == "max_nesting")
    fb = next(f for f in b.findings if f.rule == "max_nesting")
    # Symbol-scoped: same symbol -> same key even though the line moved.
    assert finding_key(fa.rule, fa.file, fa.symbol) == finding_key(fb.rule, fb.file, fb.symbol)


@requires_tree_sitter
def test_nesting_scope_filtering(tmp_path: Path) -> None:
    """Only in-scope files produce nesting findings (symbol-scoped pass)."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", _DEEP_SOURCE),
        _scanned("pkg/b.py", _DEEP_SOURCE),
    ]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules(max_nesting=3), changed_files=["pkg/a.py"])
    files_flagged = {n.file for n in report.nesting}
    assert files_flagged == {"pkg/a.py"}


@requires_tree_sitter
def test_nesting_is_deterministic(tmp_path: Path) -> None:
    """analyze() twice -> identical nesting findings."""
    db_path = _init_db(tmp_path)
    files = [
        _scanned("pkg/a.py", _DEEP_SOURCE),
        _scanned("pkg/b.py", _DEEP_SOURCE),
    ]
    first = ArchitectureAnalyzer(db_path, scanned_files=files).analyze(
        ArchitectureRules(max_nesting=3)
    )
    second = ArchitectureAnalyzer(db_path, scanned_files=files).analyze(
        ArchitectureRules(max_nesting=3)
    )
    assert first.nesting == second.nesting


def test_nesting_skipped_when_tree_sitter_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Degrade honestly: no parser -> 'max_nesting:tree-sitter-unavailable', no finding."""
    db_path = _init_db(tmp_path)
    files = [_scanned("pkg/a.py", _DEEP_SOURCE)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    monkeypatch.setattr(analyzer._parser, "is_available", lambda: False)

    report = analyzer.analyze(ArchitectureRules(max_nesting=3))
    assert report.nesting == ()
    assert "max_nesting:tree-sitter-unavailable" in report.skipped
    assert not [f for f in report.findings if f.rule == "max_nesting"]


@requires_tree_sitter
def test_max_depth_and_max_nesting_are_distinct_signals(tmp_path: Path) -> None:
    """Directory nesting (max_depth) and code nesting (max_nesting) must not conflate.

    A deeply-code-nested function in a shallow directory yields a high
    ``max_nesting`` but a low ``max_depth`` — proving the two metrics are
    independent signals on the same :class:`QualityMetrics`.
    """
    db_path = _init_db(tmp_path)
    # File at the repo root (directory depth 0) but a 4-deep code body.
    files = [_scanned("flat.py", _DEEP_SOURCE)]
    analyzer = ArchitectureAnalyzer(db_path, scanned_files=files)
    report = analyzer.analyze(ArchitectureRules(max_nesting=3))

    assert isinstance(report.metrics, QualityMetrics)
    assert report.metrics.max_depth == 0  # no '/' in the path -> directory depth 0
    assert report.metrics.max_nesting == 4  # code block-nesting
    assert report.metrics.max_depth != report.metrics.max_nesting
