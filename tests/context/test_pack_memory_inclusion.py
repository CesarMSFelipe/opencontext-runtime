"""CTX-003 integration tests: a real pack includes relevant approved memory.

DOC2 §13.2 pack pipeline has an explicit "memory recall" stage; CTX-003 ("pack
incluye memoria relevante") requires that a saved+approved memory record lands
in ``included[]`` of a real pack and is counted by ``context.memory_hits`` —
not merely used as a ranking boost.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from opencontext_core.compat import UTC
from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryLifecycle,
    MemoryRecord,
)
from opencontext_core.models.context import ContextItem, ContextPriority
from opencontext_core.runtime import OpenContextRuntime
from tests.core.conftest import create_sample_project, write_config


def _approved_memory(key: str, content: str) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=f"mem-{key.replace(':', '-')}",
        layer=MemoryLayer.SEMANTIC,
        key=key,
        content=content,
        confidence=0.9,
        decay_policy=DecayPolicy(enabled=False),
        created_at=now,
        updated_at=now,
        lifecycle=MemoryLifecycle.ACTIVE,
    )


def _is_memory_included(item: ContextItem) -> bool:
    return item.source_type == "memory" or item.metadata.get("retrieval_source") == "memory"


def test_planner_plan_surfaces_memory_records_as_candidates(tmp_path: Path) -> None:
    """CTX-003: the planner's memory-recall stage is live in the pack path —
    ``plan()`` surfaces approved memory-store records as memory-sourced evidence."""
    from opencontext_core.memory.graph import LocalMemoryStore
    from opencontext_core.retrieval.contracts import EvidenceRequest, RetrievalSurface
    from opencontext_core.retrieval.planner import RetrievalPlanner

    store = LocalMemoryStore(tmp_path / "memory.db")
    store.write(
        _approved_memory(
            "auth:audit-decision",
            "AuthService.login must always call audit_login so authentication is auditable.",
        )
    )

    class _Source:
        name = "fixture"

        def retrieve(self, query: str, limit: int) -> list[ContextItem]:
            return [
                ContextItem(
                    id="file:src/auth.py",
                    content="class AuthService: ...",
                    source="src/auth.py",
                    source_type="file",
                    priority=ContextPriority.P1,
                    tokens=10,
                    score=0.7,
                )
            ]

    planner = RetrievalPlanner([_Source()], memory_store=store)
    plan = planner.plan(
        EvidenceRequest(
            query="audit the AuthService login authentication",
            root=tmp_path,
            surface=RetrievalSurface.RUNTIME,
            max_tokens=2000,
            risk_level="normal",
        ),
        top_k=10,
    )

    memory_evidence = [item for item in plan.evidence if item.source_type == "memory"]
    assert memory_evidence, (
        "plan() must include memory-store records as candidates "
        f"(got sources: {[item.source for item in plan.evidence]})"
    )
    assert "audit_login" in memory_evidence[0].content


def test_real_pack_includes_relevant_approved_memory(tmp_path: Path) -> None:
    """CTX-003: pack includes relevant memory — a memory saved+approved BEFORE the
    pack build lands in ``included[]`` of a real runtime pack for a matching query
    and ``context.memory_hits >= 1``."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )
    runtime.index_project(project_root)

    store = getattr(runtime, "_v2_memory_store", None)
    assert store is not None, "the pack path must have a wired memory store"
    store.write(
        _approved_memory(
            "auth:audit-decision",
            "AuthService.login must always call audit_login so authentication is auditable.",
        )
    )

    pack = runtime.build_context_pack("audit the AuthService login authentication", max_tokens=2000)

    memory_items = [item for item in pack.included if _is_memory_included(item)]
    assert memory_items, (
        "a relevant approved memory must land in included[] "
        f"(included sources: {[item.source for item in pack.included]})"
    )
    assert "audit_login" in memory_items[0].content
    assert pack.context is not None, "the mandatory pack metrics block must be present"
    assert pack.context.memory_hits >= 1
