"""Tests for S2 + S3: adapter sync_state honest status (no fake noop).

S3: claude-code returns {"status":"ok",...}, others return not_configured.
S2: sync_state carries context_pack_hash after build_for_phase persists it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from opencontext_sdd.agents import registry


def test_no_adapter_returns_bare_noop() -> None:
    """No adapter must return bare {"status":"noop"} from sync_state."""
    for name, cls in registry.ADAPTERS.items():
        adapter = cls()
        result = adapter.sync_state()
        assert result.get("status") != "noop", (
            f"Adapter {name!r} returns bare 'noop' from sync_state — "
            "use 'not_configured' or 'ok' instead."
        )


def test_claude_code_sync_state_is_ok_or_not_configured() -> None:
    """claude-code adapter sync_state must return status ok or not_configured."""
    cls = registry.ADAPTERS["claude-code"]
    adapter = cls()
    result = adapter.sync_state()
    assert result.get("status") in ("ok", "not_configured"), (
        f"claude-code sync_state returned unexpected status: {result!r}"
    )


def test_claude_code_sync_state_exports_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """claude-code adapter sync_state exports memory and returns count + path."""
    from opencontext_core.memory_usability.context_repository import ContextRepository

    # Store items in the same root the adapter will use.
    repo = ContextRepository(tmp_path)
    repo.store(content="test memory entry", kind="fact", source="test")

    export_path = tmp_path / "sync_export.json"

    cls = registry.ADAPTERS["claude-code"]
    adapter = cls(project_root=tmp_path, export_path=export_path)
    result = adapter.sync_state()

    assert result["status"] == "ok"
    assert result["exported"] >= 1
    assert Path(result["path"]).exists()


def test_other_adapters_return_not_configured() -> None:
    """All adapters except claude-code return not_configured status."""
    skip = {"claude-code"}
    for name, cls in registry.ADAPTERS.items():
        if name in skip:
            continue
        adapter = cls()
        result = adapter.sync_state()
        assert result.get("status") == "not_configured", (
            f"Adapter {name!r} returned {result!r} instead of not_configured"
        )
        assert result.get("adapter") == name, (
            f"Adapter {name!r} sync_state missing 'adapter' key"
        )


def test_sync_state_carries_substrate_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After build_for_phase persists the report, sync_state includes the hash (S2)."""
    from opencontext_core.agentic.context_substrate import ContextSubstrateBuilder

    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

    # Set up a minimal indexed project.
    oc_dir = tmp_path / ".opencontext"
    oc_dir.mkdir()
    kg = {"nodes": [{"id": "a"}, {"id": "b"}]}
    (oc_dir / "knowledge_graph.json").write_text(json.dumps(kg))

    builder = ContextSubstrateBuilder(root=tmp_path)
    report = builder.build_for_phase(task="test", phase="explore", budget=8000)
    assert report.context_pack_hash is not None

    # The substrate report must be persisted so adapters can read it.
    report_files = list(tmp_path.rglob("substrate_report.json"))
    assert report_files, "build_for_phase must persist substrate_report.json"

    saved = json.loads(report_files[0].read_text())
    assert saved.get("context_pack_hash") == report.context_pack_hash
