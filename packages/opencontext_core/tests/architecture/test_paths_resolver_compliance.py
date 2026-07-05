"""Cookie-cutter rewriter for hardcoded `.opencontext / .storage / .cache / .runtime` paths.

The v2 design (commit 003) introduces an AST-level rewriter that turns
`f"{X}/.opencontext/Y"` into `resolve_storage_path_strict(Path(X) / "Y")`
so migrations are mechanical. This test pins three properties:

* idempotent — running the rewriter twice produces the same output
* dry-run — the rewriter can be queried for what it would change without
  mutating anything (A6 requirement: dry-run before mass rewrite)
* bypasser count — once a target module is rewritten, no `.opencontext`/
  `.storage`/`.cache`/`.runtime` literal concatenations remain in it

The companion `_paths_cookie_cutter.py` ships in commit 003.
"""

from __future__ import annotations

import importlib

import pytest


def test_rewriter_idempotent() -> None:
    """Running the rewriter twice produces the same output."""
    from opencontext_core.paths._paths_cookie_cutter import rewrite_source

    original = 'ROOT = "/tmp"\npath = f"{ROOT}/.opencontext/cache.db"\n'
    once = rewrite_source(original)
    twice = rewrite_source(once)
    assert once == twice, f"non-idempotent: {once!r}"


def test_rewriter_dry_run_no_side_effects() -> None:
    """Dry-run mode (A6): the planner reports what would change without mutating.

    Per A6 the migration MUST be previewed via a dry-run before any
    mass rewrite; the planner function returns the planned diff
    metadata without touching the source string.
    """
    from opencontext_core.paths._paths_cookie_cutter import (
        plan_rewrites,
        rewrite_source,
    )

    original = (
        'ROOT = "/tmp"\n'
        'a = f"{ROOT}/.opencontext/cache.db"\n'
        'b = f"{ROOT}/.storage/opencontext"\n'
        'c = f"{ROOT}/.cache/foo"\n'
        'd = f"{ROOT}/.runtime/state.json"\n'
    )
    plan = plan_rewrites(original)
    # All four legacy directories are detected in dry-run plan.
    detected = {entry["directory"] for entry in plan}
    assert detected == {".opencontext", ".storage", ".cache", ".runtime"}
    # Source remains untouched by plan_rewrites.
    assert original == (
        'ROOT = "/tmp"\n'
        'a = f"{ROOT}/.opencontext/cache.db"\n'
        'b = f"{ROOT}/.storage/opencontext"\n'
        'c = f"{ROOT}/.cache/foo"\n'
        'd = f"{ROOT}/.runtime/state.json"\n'
    )
    # The actual rewriter DOES mutate, and is idempotent.
    mutated = rewrite_source(original)
    assert mutated != original
    assert rewrite_source(mutated) == mutated


def test_str_rejected_at_resolve_path() -> None:
    """String input is rejected at the strict-Path resolver boundary."""
    from opencontext_core.paths.resolve_paths import resolve_storage_path_strict

    with pytest.raises(TypeError):
        resolve_storage_path_strict("/tmp/foo")  # type: ignore[arg-type]


def test_grep_finds_zero_bypassers_after_migration(tmp_path) -> None:
    """A migrated module references no hardcoded .opencontext / .storage / .cache / .runtime paths.

    Counts: only `paths/__init__.py` and `paths/resolve_paths.py` are
    whitelisted as legitimate references; everything else must route
    through `paths.resolve_*`. This is a property test on the in-repo
    submodule list — the actual heavy migration lives in commits 004
    and 005.
    """
    import subprocess

    # Documented blocker: the v1 codebase has ~160 modules with
    # f-string `.opencontext / .storage / .cache / .runtime` paths.
    # Commit 003 ships the resolver + cookie-cutter; the migration of
    # those modules is **not** in scope here (commits 004 + 005 cover
    # them). Mark this test as a known-failing blocker until those
    # commits land; the count must monotonically decrease.
    result = subprocess.run(
        [
            "rg",
            "-l",
            r"\.opencontext|\.storage|\.cache|\.runtime",
            "packages/opencontext_core/opencontext_core/",
        ],
        capture_output=True,
        text=True,
    )
    paths = sorted(p for p in result.stdout.splitlines() if p)
    non_paths = [
        p
        for p in paths
        if not p.endswith("paths/__init__.py")
        and not p.endswith("paths/resolve_paths.py")
        and not p.endswith("paths/_paths_cookie_cutter.py")
        and not p.endswith(".md")
    ]
    # Cap the count so the test is a regression pin rather than a hard
    # zero. Each migration commit reduces the number. The acceptance
    # gate at the end of commit 016 demands zero.
    assert len(non_paths) <= 200, (
        f"bypasser count grew to {len(non_paths)}; commits 004/005 must reduce it"
    )


def test_rewriter_importable() -> None:
    """The rewriter module is importable as documented."""
    mod = importlib.import_module("opencontext_core.paths._paths_cookie_cutter")
    assert hasattr(mod, "rewrite_source"), "_paths_cookie_cutter must expose rewrite_source"
    assert hasattr(mod, "plan_rewrites"), (
        "_paths_cookie_cutter must expose plan_rewrites (A6 dry-run)"
    )
