"""the harvest->read memory loop must close.

The harness harvests learnings into the canonical AgentMemoryStore; verify_context
must be able to READ them back (so 'this broke before' / 'we decided X' reaches the
next run's context). Before the fix _load_verified_memory read only ContextRepository,
leaving the canonical store (self._v2_memory_store) write-only / never queried.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from conftest import create_sample_project, write_config
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.retrieval.contracts import VerifiedContextRequest
from opencontext_core.runtime import OpenContextRuntime


def _runtime(tmp_path: Path) -> tuple[OpenContextRuntime, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )
    runtime.index_project(project_root)
    return runtime, project_root


def test_verify_context_reads_harvested_agent_memory(tmp_path: Path) -> None:
    runtime, root = _runtime(tmp_path)
    if not getattr(runtime, "_v2_enabled", False):
        pytest.skip("v2 memory store not enabled in this build")

    now = datetime.now(tz=UTC)
    runtime._v2_memory_store.write(
        MemoryRecord(
            id="m-loginfail",
            layer=MemoryLayer.PROCEDURAL,
            key="auth:login_failure",
            content="Authentication login broke before when the username was empty.",
            confidence=0.9,
            source_refs=[],
            decay_policy=DecayPolicy(enabled=True, half_life_days=90),
            tags=[],
            linked_nodes=[],
            created_at=now,
            updated_at=now,
        )
    )

    # The backend FTS matches the query as a phrase, so use a phrase present in the
    # stored content (real-world memory recall is a separate concern from loop closure).
    result = runtime.verify_context(
        VerifiedContextRequest(query="authentication login", root=root, include_memory=True)
    )

    blob = " ".join(item.content for item in result.memory)
    assert "broke before" in blob or any("m-loginfail" in item.id for item in result.memory)
