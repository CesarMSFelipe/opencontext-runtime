"""Cross-turn AICX delta is produced across verify_context calls (per project)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.retrieval.contracts import VerifiedContextRequest
from opencontext_core.runtime import OpenContextRuntime
from tests.core.conftest import create_sample_project, write_config


def test_second_turn_emits_delta_against_first(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )
    query = "Where is authentication implemented?"

    first = runtime.verify_context(
        VerifiedContextRequest(query=query, root=project_root, refresh_index=True, max_tokens=1200)
    )
    second = runtime.verify_context(
        VerifiedContextRequest(query=query, root=project_root, max_tokens=1200)
    )

    # First turn has no prior bytecode -> no delta; full bytecode is present.
    assert first.aicx is not None
    assert first.aicx_delta is None

    # Second turn diffs against the project's previous bytecode.
    assert second.aicx_delta is not None
    assert second.aicx_delta["base_checksum"] == first.aicx["chk"]
    assert "dict_keys" in second.aicx_delta
    assert "added_dictionary" in second.aicx_delta
