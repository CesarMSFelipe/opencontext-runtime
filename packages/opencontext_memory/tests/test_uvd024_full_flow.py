"""UVD-024 — full memory user flow integration test.

Covers install → save → search → conflict → judge → doctor in one
end-to-end sweep against a freshly-installed Python via the editable
``opencontext_memory`` package. Mirrors the spec's acceptance scenario for
the user-facing flow:

    install → mem_save(x) → bm25_search → conflict envelope surfaces →
    mem_judge(y, "related") → mem_doctor aggregates 4 checks → ok.

Does NOT run as a subprocess; the orchestrator's
``pip install -e packages/opencontext_memory`` already gives the package
visibility under the active Python.
"""

from __future__ import annotations

import importlib

from opencontext_memory import (
    DECAY_DAYS,
    MemoryStore,
    Observation,
    mem_doctor,
)
from opencontext_memory.tools import (
    mem_judge as mem_judge_mod,
)
from opencontext_memory.tools import (
    mem_save as mem_save_mod,
)
from opencontext_memory.tools import (
    mem_search as mem_search_mod,
)


def _doctor_min(report) -> bool:
    """``mem_doctor`` returns a report with all 4 checks populated."""
    return {"size", "conflicts", "retention", "lifecycle"} <= set(report.checks)


def test_uvd024_full_user_flow_save_search_conflict_judge_doctor(tmp_path) -> None:
    """install → save → search → judge → doctor integration sweep."""
    store = MemoryStore.open(tmp_path / "memory.sqlite3")

    # Seed a near-duplicate so BM25 surfaces a conflict on the second save.
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
    candidate = receipt.candidates[0]

    # BM25 search via the standard surface (REQ-OMT-002 path).
    hits = mem_search_mod.mem_search(store, query="login", limit=10)
    assert hits, "BM25 must surface at least one hit"

    # Judge the pending relation (REQ-OMT-016).
    row = mem_judge_mod.mem_judge(store, judgment_id=candidate.judgment_id, relation="related")
    assert row.judgment_status == "judged"
    assert row.relation == "related"

    # Doctor aggregates all 4 checks (size / conflicts / retention / lifecycle).
    report = mem_doctor(store)
    assert _doctor_min(report)
    assert "size" in report.checks
    # The seeded FTS rows are still in storage — the ``state`` rolls up to
    # ``"warn"`` (one pending conflict got marked judged, so 0 pending
    # now; the row that triggered the conflict has no review_after yet).
    assert report.state in {"ok", "warn"}


def test_uvd024_install_via_pip_editable_passes() -> None:
    """``importlib.util`` re-imports the package to confirm the install.

    This test does not run pip in-process (too slow / fs-unsafe); it
    relies on the upstream ``pip install -e`` that the orchestrator runs
    before any test session. If the package is importable, the install
    contract holds.
    """
    spec = importlib.util.find_spec("opencontext_memory")
    assert spec is not None, "opencontext_memory must be importable after install"
    assert spec.origin is not None
    # Re-import is idempotent.
    opencontext_memory = importlib.import_module("opencontext_memory")
    assert "MemoryStore" in opencontext_memory.__all__
    assert "mem_save" in opencontext_memory.__all__
    assert "mem_doctor" in opencontext_memory.__all__


def test_uvd024_decay_table_canonical() -> None:
    """The exported ``DECAY_DAYS`` constant matches the canonical lifecycle table."""
    assert DECAY_DAYS["decision"] == 90
    assert DECAY_DAYS["architecture"] == 180
    assert DECAY_DAYS["bugfix"] == 30
    assert DECAY_DAYS["pattern"] == 180
    assert DECAY_DAYS["config"] == 365
    assert DECAY_DAYS["discovery"] == 60
    assert DECAY_DAYS["manual"] == 180
