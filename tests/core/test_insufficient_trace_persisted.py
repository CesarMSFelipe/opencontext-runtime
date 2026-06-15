"""the verify_context insufficient path must persist a loadable trace.

Before the fix, the `except MemoryStoreError` branch returned a fresh
`uuid4().hex` trace_id that was never written to disk, so `load_trace(trace_id)`
(and the API GET /v1/traces/{id}) raised "Trace not found" — the audit record
vanished exactly when context was withheld.
"""

from __future__ import annotations

from pathlib import Path

from conftest import write_config

from opencontext_core.retrieval.contracts import VerifiedContextRequest
from opencontext_core.runtime import OpenContextRuntime


def test_verify_context_insufficient_persists_loadable_trace(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    # No project indexed -> no manifest -> verify_context hits the insufficient branch.
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )

    result = runtime.verify_context(
        VerifiedContextRequest(
            query="Where is authentication implemented?",
            root=project_root,
            refresh_index=False,
            max_tokens=800,
        )
    )

    assert result.trust_decision.status == "insufficient"
    # The returned trace_id MUST resolve to a persisted trace (content fields are
    # redacted by the TraceSanitizer, same as the happy path — assert identity only).
    loaded = runtime.load_trace(result.trace_id)
    assert loaded.run_id == result.trace_id
    assert loaded.workflow_name == "context_pack.local"
