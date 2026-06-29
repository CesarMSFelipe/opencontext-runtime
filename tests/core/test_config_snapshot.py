"""PR-013 SPEC-CLI-013-04: per-session config snapshot."""

from __future__ import annotations

from pathlib import Path

import yaml

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.config_snapshot import snapshot_path, write_snapshot


def test_write_snapshot_persists_resolved_config(tmp_path: Path) -> None:
    config = OpenContextConfig.model_validate(default_config_data())
    path = write_snapshot(config, "sess-abc123", tmp_path, provenance={"profile": "defaults"})
    assert path == snapshot_path(tmp_path, "sess-abc123")
    assert path.exists()
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["session_id"] == "sess-abc123"
    assert doc["config"]["profile"] == "balanced"
    assert doc["provenance"] == {"profile": "defaults"}


def test_snapshot_written_under_session_dir(tmp_path: Path) -> None:
    write_snapshot(default_config_data(), "sess-xyz", tmp_path)
    expected = tmp_path / ".opencontext" / "sessions" / "sess-xyz" / "config-snapshot.yaml"
    assert expected.exists()
