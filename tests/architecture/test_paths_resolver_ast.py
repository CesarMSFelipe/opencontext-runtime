"""AST gate: flag productive code that hand-builds storage/workspace paths.

Amendment-3 P1.5 source-of-truth gate (see ``design.md`` acceptance
criterion #2 and ``tasks/commit-003-runtime-paths-helper.md``).

The :func:`scan_hardcoded_paths` helper lives in
``opencontext_core.paths._paths_cookie_cutter`` (alongside the regex
cookie-cutter rewriter). The scanner walks
``packages/opencontext_core/opencontext_core/`` and flags productive
code that hand-builds a forbidden storage path::

    Path(root) / ".opencontext"   ->  ast.BinOp(Div, _, Constant)
    Path(root) / ".storage"
    Path(root) / ".runtime"
    Path(root) / ".cache"
    open(f"{root}/.storage/x.db")     ->  ast.Call(open, JoinedStr)
    sqlite3.connect(f"{root}/.storage/x.db")

Allowlisted (NOT flagged):
    * top-level dirs: tests/, docs/, examples/, benchmarks/, __pycache__,
      build/, dist/
    * the sanctioned path-construction owners: ``paths/__init__.py``,
      ``paths/resolve_paths.py``, ``paths/_paths_cookie_cutter.py``
    * module/function/class docstrings (``ast.Expr`` of a bare
      ``ast.Constant``)
    * attribute accesses like ``x.storage.mode`` — only STRING leaves
      count, never identifier segments

The cookie-cutter rewriter is the *suggested* remediation path; this
test only verifies the AST gate. Remediation lives in a follow-up commit
per strict TDD (this test MUST FAIL initially when productive code has
hardcoded paths).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.paths._paths_cookie_cutter import (
    PROD_ROOT,
    _is_docstring,
    _is_leftmost_div,
    _string_contains_forbidden,
    scan_hardcoded_paths,
)


@pytest.fixture()
def scanner():
    """Return a callable that scans for hardcoded paths in productive code.

    Yields ``scan_hardcoded_paths`` so tests can capture findings and
    assert shape. The fixture has no teardown; the scanner is a pure
    AST reader.
    """
    return scan_hardcoded_paths


# ---------------------------------------------------------------------------
# Gate (strict TDD: must FAIL initially when productive code has hardcoded paths)
# ---------------------------------------------------------------------------


def test_ast_finds_zero_hardcoded_paths(scanner) -> None:
    """The productive tree must contain zero hand-built storage paths.

    Strict TDD: this test FAILS as long as productive code builds
    ``Path(root) / ".opencontext"`` (or any other forbidden segment).
    Remediation is a follow-up commit (cookie-cutter rewrite per module);
    this test is the ratchet that prevents regression.
    """
    findings = scanner()
    assert findings == [], (
        "Hardcoded storage paths detected in productive code "
        "(route through `paths.resolve_*` or add to ALLOWLIST with "
        "a reason in review):\n"
        + "\n".join(f"  {rel}:{lineno}  {shape}" for rel, lineno, shape in findings)
    )


# ---------------------------------------------------------------------------
# Allowlist coverage
# ---------------------------------------------------------------------------


def test_ast_allowlist_excludes_tests_docs(tmp_path: Path) -> None:
    """Test/docs/bench/examples are excluded by ``_is_productive``.

    The scanner's allowlist walks ``path.parts`` and bails out when any
    top-level segment matches ``ALLOWLIST_TOP``. We construct a fake
    ``tests/`` and ``docs/`` tree containing a hardcoded-path violation
    and assert the scanner does NOT flag those excluded paths (while it
    still flags productive code at the fake root).
    """
    fake_root = tmp_path / "fake_prod"
    fake_root.mkdir()

    # Mirror a productive tree under the fake root.
    (fake_root / "productive.py").write_text(
        "from pathlib import Path\ndef f(root): return Path(root) / '.opencontext'\n",
        encoding="utf-8",
    )

    # Mirror excluded dirs. Each carries a violation that MUST be ignored.
    for excluded in ("tests", "docs", "examples", "benchmarks"):
        excluded_dir = fake_root / excluded / "sub"
        excluded_dir.mkdir(parents=True)
        (excluded_dir / "sample.py").write_text(
            "from pathlib import Path\ndef f(root): return Path(root) / '.opencontext'\n",
            encoding="utf-8",
        )

    findings = scan_hardcoded_paths(root=fake_root)
    flagged = [rel for rel, _, _ in findings]

    # Only ``productive.py`` should be flagged; tests/docs/etc. MUST be skipped.
    assert all("tests/" not in rel for rel in flagged), (
        f"Scanner must skip tests/, but flagged: {flagged}"
    )
    assert all("docs/" not in rel for rel in flagged), (
        f"Scanner must skip docs/, but flagged: {flagged}"
    )
    assert all("examples/" not in rel for rel in flagged), (
        f"Scanner must skip examples/, but flagged: {flagged}"
    )
    assert all("benchmarks/" not in rel for rel in flagged), (
        f"Scanner must skip benchmarks/, but flagged: {flagged}"
    )
    assert any("productive.py" in rel for rel in flagged), (
        f"productive code at root should still be flagged: {flagged}"
    )


def test_ast_allowlist_excludes_paths_owners(tmp_path: Path) -> None:
    """Files in the paths/ subpackage are the resolver — they MUST be allowed.

    The resolver implementation constructs the very paths the scanner
    looks for; flagging it would mean the resolver itself is forbidden,
    which is the opposite of the design intent.
    """
    fake_root = tmp_path / "fake_with_paths"
    # Mirror the real package layout: opencontext_core/opencontext_core/paths/
    pkg = fake_root / "opencontext_core" / "opencontext_core"
    paths_pkg = pkg / "paths"
    paths_pkg.mkdir(parents=True)
    (paths_pkg / "__init__.py").write_text(
        "from pathlib import Path\ndef resolve(root): return Path(root) / '.opencontext'\n",
        encoding="utf-8",
    )
    (pkg / "other_module.py").write_text(
        "from pathlib import Path\ndef f(root): return Path(root) / '.storage'\n",
        encoding="utf-8",
    )

    findings = scan_hardcoded_paths(root=fake_root)
    flagged = [rel for rel, _, _ in findings]
    # The paths/ owner MUST be allowlisted; ``other_module.py`` MUST be flagged.
    # Use a path-segment check (``/paths/``) instead of substring match so
    # the test does not trip on the tmp_path prefix.
    assert not any("/paths/" in rel for rel in flagged), (
        f"paths/ subpackage must be allowlisted, but got: {flagged}"
    )
    assert any("other_module" in rel for rel in flagged), (
        f"productive code outside the owner should still be flagged: {flagged}"
    )


# ---------------------------------------------------------------------------
# Detector unit checks — the scanner's primitive shape must work as advertised
# ---------------------------------------------------------------------------


def test_docstring_is_skipped() -> None:
    """``_is_docstring`` returns True for module/function/class docstrings."""
    import ast

    src = 'def f():\n    """Docstring mentioning .opencontext."""\n    return 1\n'
    tree = ast.parse(src)
    # The function body's first statement is the docstring ``ast.Expr``.
    fn_body = tree.body[0].body  # type: ignore[attr-defined]
    first_stmt = fn_body[0]
    assert _is_docstring(first_stmt), (
        "first statement of a function body must be skipped as a docstring"
    )


def test_leftmost_div_returns_true_for_leaf() -> None:
    """``_is_leftmost_div`` returns True for a single BinOp-Div (left is not a Div).

    Direct unit test on the helper rather than via end-to-end scan, so a
    regression in the chain-structure logic is caught immediately.
    """
    import ast

    src = "a / b"
    tree = ast.parse(src)
    binop = tree.body[0].value  # type: ignore[attr-defined]
    assert isinstance(binop, ast.BinOp)
    assert _is_leftmost_div(binop) is True


def test_leftmost_div_returns_false_for_outer() -> None:
    """``_is_leftmost_div`` returns False for the OUTER BinOp in a chain.

    For ``a / b / c`` the OUTER BinOp has ``left`` that IS a BinOp-Div
    (the inner chain). The LEFTMOST (innermost) BinOp has ``left`` that
    is a Name — only the innermost is "leftmost".
    """
    import ast

    src = "a / b / c"
    tree = ast.parse(src)
    outer = tree.body[0].value  # type: ignore[attr-defined]
    assert isinstance(outer, ast.BinOp)
    # Outer is NOT leftmost -> False.
    assert _is_leftmost_div(outer) is False
    # Inner (outer.left) IS leftmost -> True.
    inner = outer.left
    assert isinstance(inner, ast.BinOp)
    assert _is_leftmost_div(inner) is True


def test_string_contains_forbidden_skips_attribute_access() -> None:
    """``_string_contains_forbidden`` does not match ``x.storage.mode``.

    The detector must NOT flag attribute accesses — only string literals.
    Otherwise ``qrc.storage.mode`` would trip every gate.
    """
    import ast

    src = "x.storage.mode"
    tree = ast.parse(src)
    attr_node = tree.body[0].value  # type: ignore[attr-defined]
    assert _string_contains_forbidden(attr_node) is None


def test_string_contains_forbidden_matches_literal() -> None:
    """``_string_contains_forbidden`` matches a bare string with a forbidden segment."""
    import ast

    src = '".opencontext"'
    tree = ast.parse(src)
    const_node = tree.body[0].value  # type: ignore[attr-defined]
    assert _string_contains_forbidden(const_node) == ".opencontext"


def test_guard_flags_a_seeded_path_violation(tmp_path: Path) -> None:
    """The detector MUST FAIL on a seeded ``Path(root) / '.opencontext'``.

    Ensures the scanner's primitive shapes are wired correctly. The
    cookie-cutter rewriter is the suggested remediation path; this
    test is the gate that proves the scanner actually fires.
    """
    fake_root = tmp_path / "seeded"
    fake_root.mkdir()
    (fake_root / "module.py").write_text(
        "from pathlib import Path\n"
        "def bad(root: Path) -> Path:\n"
        "    return Path(root) / '.opencontext'\n",
        encoding="utf-8",
    )

    findings = scan_hardcoded_paths(root=fake_root)
    assert findings, "scanner must detect a seeded Path(root) / '.opencontext'"
    assert all(shape.startswith("Path()") for _, _, shape in findings)


# ---------------------------------------------------------------------------
# Smoke checks — the real productive tree is the actual source of truth
# ---------------------------------------------------------------------------


def test_prod_root_resolves_to_opencontext_core() -> None:
    """``PROD_ROOT`` points at ``packages/opencontext_core/``.

    The scanner's contract is fixed at module import time: it walks the
    installed package, not an arbitrary directory. A drift here would
    silently turn the gate into a no-op.
    """
    assert PROD_ROOT.name == "opencontext_core"
    assert PROD_ROOT.exists()
    assert PROD_ROOT.is_dir()


def test_scanner_does_not_flag_paths_module() -> None:
    """The sanctioned owners (``paths/``) are excluded from a real scan.

    Catches a regression where someone removes ``_OWNER_PREFIXES`` —
    the resolver implementation would then be flagged, which is the
    opposite of the design.
    """
    findings = scan_hardcoded_paths()
    bad = [rel for rel, _, _ in findings if "/paths/" in rel]
    assert not bad, f"paths/ owners must be excluded, but found: {bad}"
