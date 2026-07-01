"""Tests for the eager memory tools (PR2.b / PR2.c).

Per strict-TDD: this file is the source of truth for the eager tool contracts.
The corresponding ``tools/*.py`` modules are written to satisfy these tests.

T2.21 — ``test_REQ_OMT_001_save_*`` (RED, PR2.b). ``tools/mem_save.py``
lands in the same apply batch to turn it GREEN.

T2.23 — ``test_REQ_OMT_002..007`` (RED, PR2.c.i). Six tools land in the
same apply batch to turn them GREEN:
``mem_search``, ``mem_context``, ``mem_session_summary``, ``mem_get_observation``,
``mem_save_prompt``, ``mem_current_project``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from opencontext_memory import MemoryStore, Observation
from opencontext_memory.tools import (
    mem_context as mem_context_mod,
)
from opencontext_memory.tools import (
    mem_current_project as mem_current_project_mod,
)
from opencontext_memory.tools import (
    mem_get_observation as mem_get_observation_mod,
)
from opencontext_memory.tools import mem_save as mem_save_mod
from opencontext_memory.tools import (
    mem_save_prompt as mem_save_prompt_mod,
)
from opencontext_memory.tools import (
    mem_search as mem_search_mod,
)
from opencontext_memory.tools import (
    mem_session_summary as mem_session_summary_mod,
)


def _make_store(tmp_path) -> MemoryStore:
    return MemoryStore.open(tmp_path / "memory.sqlite3")


def _write_git_repo(path, *, remote_url: str | None = None) -> Path:
    """Create a fake git repo at ``path/.git`` with an optional remote URL."""
    path = Path(path)
    (path / ".git").mkdir(parents=True, exist_ok=True)
    lines = ["[core]", "    repositoryformatversion = 0"]
    if remote_url is not None:
        lines += ['[remote "origin"]', f"    url = {remote_url}"]
    (path / ".git" / "config").write_text("\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------------------
# REQ-OMT-001 — mem_save happy path (T2.21)
# ---------------------------------------------------------------------------


def test_REQ_OMT_001_save_no_candidates_returns_clean_receipt(store_db) -> None:
    """First save into an empty store: no BM25 hit clears the floor, so
    ``judgment_required`` is False and the receipt carries the new row id."""
    store = _make_store(store_db)
    receipt = mem_save_mod.mem_save(
        store=store,
        session_id="sess-1",
        project="P",
        title="Fix login bug",
        content="users get 500 on POST /login",
        type="decision",
    )

    assert receipt.judgment_required is False
    assert receipt.candidates == []
    assert receipt.receipt.id >= 1
    assert receipt.receipt.title == "Fix login bug"


def test_REQ_OMT_001_save_with_conflict_returns_envelope_with_judgment_id(store_db) -> None:
    """When a near-duplicate exists, ``judgment_required`` is True AND each
    candidate has a ``judgment_id`` matching the correlation-handle pattern
    AND a ``pending`` relation row is inserted in ``memory_relations``.
    """
    store = _make_store(store_db)

    # Seed a near-duplicate so BM25 matches above the floor.
    store.write(
        Observation(
            session_id="sess-1",
            title="Fix login bug",
            content="users get 500 on POST /login",
            project="P",
            type="decision",
        )
    )

    receipt = mem_save_mod.mem_save(
        store=store,
        session_id="sess-2",
        project="P",
        title="Login 500 again",
        content="users still get 500 on POST /login",
        type="decision",
    )

    assert receipt.judgment_required is True
    assert len(receipt.candidates) >= 1
    cand = receipt.candidates[0]
    assert re.match(r"^rel-[0-9a-f]{8,}$", cand.judgment_id), (
        f"judgment_id {cand.judgment_id!r} does not match ^rel-[0-9a-f]{(8,)}$"
    )
    assert cand.judgment_status == "pending"

    # And the pending relation row is actually persisted.
    with store._connect() as conn:
        row = conn.execute(
            "SELECT relation, judgment_status FROM memory_relations WHERE judgment_id = ?",
            (cand.judgment_id,),
        ).fetchone()
    assert row is not None
    assert row["judgment_status"] == "pending"


def test_REQ_OMT_001_save_rejects_missing_content(store_db) -> None:
    """Empty content is a hard error (matches the spec's "invalid" branch)."""
    store = _make_store(store_db)

    with pytest.raises(ValueError, match=r"content_required"):
        mem_save_mod.mem_save(
            store=store,
            session_id="sess-1",
            project="P",
            title="t",
            content="",
            type="decision",
        )


def test_REQ_OMT_001_save_persists_observation_with_given_fields(store_db) -> None:
    """Triangulation: a successful save lands in ``observations`` with the
    supplied ``title``, ``content``, ``project``, and ``type`` so a later
    ``mem_get_observation`` would find it.
    """
    store = _make_store(store_db)
    receipt = mem_save_mod.mem_save(
        store=store,
        session_id="sess-1",
        project="P",
        title="Auth refactor",
        content="extract auth middleware into its own module",
        type="decision",
    )

    with store._connect() as conn:
        row = conn.execute(
            "SELECT title, content, project, type FROM observations WHERE id = ?",
            (receipt.receipt.id,),
        ).fetchone()
    assert dict(row) == {
        "title": "Auth refactor",
        "content": "extract auth middleware into its own module",
        "project": "P",
        "type": "decision",
    }


# ---------------------------------------------------------------------------
# REQ-OMT-002 — mem_search BM25 (T2.23a)
# ---------------------------------------------------------------------------


def test_REQ_OMT_002_search_bm25_ranking_and_unknown_query_returns_empty(store_db) -> None:
    """BM25 ranks lower-is-better: ``mem_search("login")`` lands the login row
    first. An unknown query (``zzzqqqxxx``) returns an empty list, NOT an
    error — the spec is explicit that BM25 misses are silent.
    """
    store = _make_store(store_db)
    store.write(
        Observation(
            session_id="s-1",
            title="Fix login bug",
            content="users get 500 on POST /login",
            project="P",
            type="decision",
        )
    )
    store.write(
        Observation(
            session_id="s-1",
            title="Auth refactor",
            content="extract auth middleware into its own module",
            project="P",
            type="decision",
        )
    )

    hits = mem_search_mod.mem_search(store, query="login", limit=10)
    assert hits, "expected at least one BM25 hit for 'login'"
    assert hits[0]["title"] == "Fix login bug"

    empty = mem_search_mod.mem_search(store, query="zzzqqqxxx", limit=10)
    assert empty == []


# ---------------------------------------------------------------------------
# REQ-OMT-003 — mem_context scoped by project (T2.23b)
# ---------------------------------------------------------------------------


def test_REQ_OMT_003_context_filters_by_project(store_db) -> None:
    """When ``project="P1"`` is passed, observations in P2 are filtered out."""
    store = _make_store(store_db)
    store.write(
        Observation(session_id="s-1", title="P1 thing", content="c", project="P1", type="decision")
    )
    store.write(
        Observation(session_id="s-1", title="P2 thing", content="c", project="P2", type="decision")
    )

    rows = mem_context_mod.mem_context(store, project="P1", scope="project", limit=20)
    titles = [r["title"] for r in rows]
    assert "P1 thing" in titles
    assert "P2 thing" not in titles


# ---------------------------------------------------------------------------
# REQ-OMT-004 — mem_session_summary persists 6 fields + rejects empty goal
# ---------------------------------------------------------------------------


def test_REQ_OMT_004_session_summary_persists_six_fields(store_db) -> None:
    """All six structured fields land in the ``sessions`` row. List fields are
    JSON-encoded so the cell stays a single TEXT value.
    """
    store = _make_store(store_db)
    mem_session_summary_mod.mem_session_summary(
        store=store,
        session_id="sess-1",
        goal="Ship PR2.c.i",
        instructions="Strict TDD, no Co-Authored-By",
        discoveries=["BM25 ranks lower-is-better", "FTS5 needs sanitization"],
        accomplished=["T2.23 RED", "T2.24 GREEN"],
        next_steps=["PR2.c.ii", "PR2.d"],
        relevant_files=[
            "packages/opencontext_memory/opencontext_memory/tools/mem_save.py",
        ],
    )

    with store._connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", ("sess-1",)).fetchone()

    assert row is not None, "session_summary must persist a row keyed by session_id"
    assert row["goal"] == "Ship PR2.c.i"
    assert row["instructions"] == "Strict TDD, no Co-Authored-By"
    assert json.loads(row["discoveries"]) == [
        "BM25 ranks lower-is-better",
        "FTS5 needs sanitization",
    ]
    assert json.loads(row["accomplished"]) == ["T2.23 RED", "T2.24 GREEN"]
    assert json.loads(row["next_steps"]) == ["PR2.c.ii", "PR2.d"]
    assert json.loads(row["relevant_files"]) == [
        "packages/opencontext_memory/opencontext_memory/tools/mem_save.py",
    ]


def test_REQ_OMT_004_session_summary_rejects_empty_goal(store_db) -> None:
    """An empty ``goal`` raises ``ValueError("goal_required")`` and persists nothing."""
    store = _make_store(store_db)

    with pytest.raises(ValueError, match=r"^goal_required$"):
        mem_session_summary_mod.mem_session_summary(
            store=store,
            session_id="sess-1",
            goal="",
            discoveries=[],
            accomplished=[],
            next_steps=[],
            relevant_files=[],
        )

    with store._connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
    assert count == 0


# ---------------------------------------------------------------------------
# REQ-OMT-005 — mem_get_observation returns record or raises MemoryNotFound
# ---------------------------------------------------------------------------


def test_REQ_OMT_005_get_observation_existing_id_returns_record(store_db) -> None:
    """A prior ``store.write`` lands a row; ``mem_get_observation(id)`` echoes it."""
    store = _make_store(store_db)
    new_id = store.write(
        Observation(
            session_id="s-1",
            title="t",
            content="c",
            project="P",
            type="decision",
        )
    )

    obs = mem_get_observation_mod.mem_get_observation(store, observation_id=new_id)
    assert obs["id"] == new_id
    assert obs["title"] == "t"
    assert obs["content"] == "c"
    assert obs["project"] == "P"


def test_REQ_OMT_005_get_observation_unknown_id_raises_memory_not_found(store_db) -> None:
    """An unknown id raises :class:`MemoryNotFound` (a :class:`LookupError`
    subclass) carrying the offending id."""
    store = _make_store(store_db)

    with pytest.raises(mem_get_observation_mod.MemoryNotFound) as exc_info:
        mem_get_observation_mod.mem_get_observation(store, observation_id=9999)

    assert exc_info.value.observation_id == 9999


# ---------------------------------------------------------------------------
# REQ-OMT-006 — mem_save_prompt auto-detects project from cwd
# ---------------------------------------------------------------------------


def test_REQ_OMT_006_save_prompt_project_auto_detected_from_cwd(
    store_db, monkeypatch, tmp_path
) -> None:
    """When ``project`` is omitted, ``mem_save_prompt`` derives the project
    handle from the cwd's git origin (per REQ-OMT-007 → REQ-OMPD-001).
    """
    repo = _write_git_repo(tmp_path / "proj", remote_url="git@github.com:foo/bar.git")
    monkeypatch.chdir(repo)

    store = _make_store(store_db)
    receipt = mem_save_prompt_mod.mem_save_prompt(
        store,
        session_id="sess-1",
        content="User asked: how do I run tests?",
    )

    assert receipt.receipt.project == "bar"


# ---------------------------------------------------------------------------
# REQ-OMT-007 — mem_current_project detects from git remote (or falls back)
# ---------------------------------------------------------------------------


def test_REQ_OMT_007_current_project_detected_from_git_remote(monkeypatch, tmp_path) -> None:
    """A git repo with origin returns ``project=<slug>`` and
    ``source="git_remote"``. Slug derivation is deterministic per
    REQ-OMPD-004 (split on ``:``, ``/``, ``.git``, lowercase, kebab-case).
    """
    repo = _write_git_repo(tmp_path / "myproj", remote_url="git@github.com:foo/bar.git")
    monkeypatch.chdir(repo)

    result = mem_current_project_mod.mem_current_project()
    assert result.project == "bar"
    assert result.source == "git_remote"


def test_REQ_OMT_007_current_project_dir_basename_fallback(monkeypatch, tmp_path) -> None:
    """When no git context exists, fall back to the cwd basename."""
    plain = tmp_path / "standalone"
    plain.mkdir()
    monkeypatch.chdir(plain)

    result = mem_current_project_mod.mem_current_project()
    assert result.project == "standalone"
    assert result.source == "dir_basename"
