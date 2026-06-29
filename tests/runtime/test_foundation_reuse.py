"""Tests that PR-001 reuses shipped foundations, not duplicates (RC-014/015/016)."""

from __future__ import annotations

from pathlib import Path

import opencontext_core.runtime as runtime_pkg
import opencontext_core.runtime.run as runtime_run
from opencontext_core.agentic.receipt import AgenticReceipt
from opencontext_core.harness.run_store import RunStore
from opencontext_core.models.run_envelope import ArtifactRef
from opencontext_core.runtime.session import RuntimeSession
from opencontext_core.runtime.session_store import SessionStore


class TestReuse:
    def test_runtime_run_reuses_artifact_ref(self) -> None:
        # RuntimeRun.artifacts uses the existing ArtifactRef, not a new model.
        assert runtime_run.ArtifactRef is ArtifactRef

    def test_runtime_does_not_redefine_evidence_or_receipt(self) -> None:
        exported = set(runtime_pkg.__all__)
        assert "RunEnvelope" not in exported
        assert "AgenticReceipt" not in exported
        assert not any(name.endswith("Receipt") for name in exported)

    def test_receipt_model_is_the_shared_one(self) -> None:
        # The canonical receipt remains AgenticReceipt v2.
        assert AgenticReceipt.model_fields["schema_version"].default.startswith(
            "opencontext.agentic_receipt"
        )


class TestRunStoreUntouched:
    def test_session_store_does_not_touch_legacy_run_index(self, tmp_path: Path) -> None:
        run_store = RunStore(tmp_path)
        run_store.register("run-legacy", tmp_path / "artifacts")
        index_path = tmp_path / ".opencontext" / "runs" / "index.json"
        before = index_path.read_bytes()

        store = SessionStore(tmp_path)
        store.create_session(
            RuntimeSession(session_id="sess-1", root=str(tmp_path), task="t", profile="balanced")
        )

        assert index_path.read_bytes() == before
        assert run_store.list_run_ids() == ["run-legacy"]
        # SessionStore writes only under .opencontext/sessions/.
        session_index = tmp_path / ".opencontext" / "sessions" / "sess-1" / "runs" / "index.json"
        assert not session_index.exists()
