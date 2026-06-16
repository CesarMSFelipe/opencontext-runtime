"""surface parity — prepare_context must expose the same verification
fields (gates, risk_level, aicx) as verify_context for the same query, so CLI/MCP/API
do not disagree on trust semantics.
"""

from __future__ import annotations

from pathlib import Path

from conftest import create_sample_project, write_config
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
    return runtime, project_root


def test_prepare_context_exposes_parity_fields(tmp_path: Path) -> None:
    runtime, project_root = _runtime(tmp_path)
    query = "Where is authentication implemented?"

    prepared = runtime.prepare_context(
        query, root=project_root, refresh_index=True, max_tokens=1200
    )
    verified = runtime.verify_context(
        VerifiedContextRequest(query=query, root=project_root, max_tokens=1200)
    )

    # prepare_context now carries gates / risk_level / aicx ...
    assert prepared.gates
    assert prepared.risk_level
    # ... and they agree with verify_context for the same query (surface parity).
    assert {g.name for g in prepared.gates} == {g.name for g in verified.gates}
    assert prepared.risk_level == verified.risk_level.value
