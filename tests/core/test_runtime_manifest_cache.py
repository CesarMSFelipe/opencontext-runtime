"""Perf guard: the runtime caches the parsed manifest across retrieval calls.

Parsing the whole-repo manifest JSON through Pydantic is query-independent and
was the dominant per-query cost on large repos (it recurred on every
``prepare_context`` / ``verify_context`` call, and the benchmark parsed it up to
three times per case). The cache must:

  * elide the redundant parse on a warm call (the latency fix), counted by the
    number of times the underlying store actually parses — a deterministic,
    machine-independent proxy for the wall-clock win; and
  * stay correct: a re-index that rewrites the manifest must invalidate the
    cache so callers observe the new on-disk manifest.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.runtime import OpenContextRuntime
from tests.core.conftest import create_sample_project, write_config


def _runtime(tmp_path: Path) -> tuple[OpenContextRuntime, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    config_path = write_config(tmp_path, project_root)
    runtime = OpenContextRuntime(
        config_path=config_path,
        storage_path=tmp_path / ".storage/opencontext",
    )
    return runtime, project_root


def _count_store_parses(runtime: OpenContextRuntime, monkeypatch) -> list[int]:
    """Wrap the store's load_manifest to count real (uncached) parses."""
    calls = [0]
    real = runtime.memory_store.load_manifest

    def _counting():  # type: ignore[no-untyped-def]
        calls[0] += 1
        return real()

    monkeypatch.setattr(runtime.memory_store, "load_manifest", _counting)
    return calls


class TestManifestParseCache:
    def test_repeated_load_manifest_parses_disk_once(self, tmp_path: Path, monkeypatch) -> None:
        runtime, project_root = _runtime(tmp_path)
        runtime.index_project(project_root)

        # index_project INVALIDATES the cache, so the next load re-reads the
        # PERSISTED (redacted) manifest from disk — never the un-redacted in-memory
        # one. So the first load after index re-parses once; the second is a cache hit.
        parses = _count_store_parses(runtime, monkeypatch)
        first = runtime.load_manifest()
        second = runtime.load_manifest()

        assert parses[0] == 1, "two loads after index should parse the disk exactly once"
        # Same parsed object handed back — proof it is the cache, not a re-parse.
        assert first is second

    def test_cold_load_parses_then_warm_load_is_free(self, tmp_path: Path, monkeypatch) -> None:
        # A runtime that did NOT index in-process (cache empty) parses once on the
        # cold call, then serves every subsequent call from the stat-keyed cache.
        runtime, project_root = _runtime(tmp_path)
        runtime.index_project(project_root)
        runtime._manifest_cache = None
        runtime._manifest_cache_sig = None

        parses = _count_store_parses(runtime, monkeypatch)
        runtime.load_manifest()  # cold: one real parse
        runtime.load_manifest()  # warm: cache hit
        runtime.load_manifest()  # warm: cache hit

        assert parses[0] == 1

    def test_prepare_context_warm_does_not_reparse_manifest(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # prepare_context loads the manifest in its preamble AND again inside
        # _build_context_pack_with_trace. With the cache, a warm prepare_context
        # must perform ZERO disk re-parses — the perf fix, asserted deterministically.
        runtime, project_root = _runtime(tmp_path)
        runtime.index_project(project_root)

        # Warm the cache (mirrors a reused runtime across benchmark cases).
        runtime.prepare_context("Where is authentication implemented?", root=project_root)

        parses = _count_store_parses(runtime, monkeypatch)
        result = runtime.prepare_context(
            "How does AuthService.login validate the username?", root=project_root
        )

        assert parses[0] == 0, "warm prepare_context re-parsed the manifest"
        assert result.included_sources, "warm pack must still deliver real evidence"

    def test_reindex_invalidates_cache(self, tmp_path: Path, monkeypatch) -> None:
        # Correctness over speed: a re-index that adds a file must be visible to the
        # very next load_manifest — the stat signature changes and forces a re-parse.
        runtime, project_root = _runtime(tmp_path)
        runtime.index_project(project_root)
        before = runtime.load_manifest()
        before_paths = {f.path for f in before.files}

        # Add a new source file and re-index: the manifest file is rewritten.
        (project_root / "src" / "billing.py").write_text(
            "def charge(amount: int) -> int:\n    return amount\n",
            encoding="utf-8",
        )
        runtime.index_project(project_root)

        after = runtime.load_manifest()
        after_paths = {f.path for f in after.files}

        assert after is not before, "cache served a stale manifest after re-index"
        assert after_paths - before_paths, "re-indexed manifest did not surface the new file"
