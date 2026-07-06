"""CFG-005/006/007/009: `config explain` payload — sources, conflicts, masking."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config_explain import explain
from opencontext_core.errors import ConfigurationError


def _write(root: Path, body: str) -> Path:
    path = root / "opencontext.yaml"
    path.write_text(body, encoding="utf-8")
    return path


# ── CFG-007: source per key ─────────────────────────────────────────────────


def test_sources_report_layer_path_and_line(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "version: 2\nproject:\n  name: demo\nharness:\n  tdd_mode: strict\n",
    )
    payload = explain(tmp_path, env={}, global_config={})
    source = payload["sources"]["harness.tdd_mode"]
    assert source["value"] == "strict"
    assert source["source"] == "project"
    assert source["path"] == str(path)
    assert source["line"] == 5  # "  tdd_mode: strict" is line 5
    # Untouched keys resolve to defaults with no file origin.
    default_source = payload["sources"]["harness.strict_tdd"]
    assert default_source["source"] == "defaults"
    assert default_source["path"] is None
    assert default_source["line"] is None


def test_effective_config_and_validation_passed(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nproject:\n  name: demo\n")
    payload = explain(tmp_path, env={}, global_config={})
    assert payload["effective_config"]["project"]["name"] == "demo"
    assert payload["validation"]["status"] == "passed"
    assert payload["unknown_keys"] == []
    assert payload["deprecated_keys"] == []


# ── Conflicts: keys set by 2+ explicit layers report losing layers ──────────


def test_conflicts_report_losing_layers(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nproject:\n  name: demo\nui_language: es\n")
    payload = explain(tmp_path, env={}, global_config={"ui_language": "en"})
    conflict = next(c for c in payload["conflicts"] if c["key"] == "ui_language")
    assert conflict["winner"] == "project"
    assert "global" in conflict["losers"]


# ── CFG-005: unknown key warns (reported, does not crash resolution) ────────


def test_unknown_key_reported_as_warning(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nproject:\n  name: demo\nbogus_key: 1\n")
    payload = explain(tmp_path, env={}, global_config={})
    assert "bogus_key" in payload["unknown_keys"]
    assert payload["validation"]["status"] == "warning"


# ── CFG-009: secrets never printed ───────────────────────────────────────────


def test_secret_values_are_masked(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "version: 2\nproject:\n  name: demo\ncapabilities:\n  github_token: ghp_secret123\n",
    )
    payload = explain(tmp_path, env={}, global_config={})
    assert payload["effective_config"]["capabilities"]["github_token"] == "***"
    source = payload["sources"]["capabilities.github_token"]
    assert source["value"] == "***"
    import json

    assert "ghp_secret123" not in json.dumps(payload)


# ── Deprecated keys carry a migration hint ───────────────────────────────────


def test_deprecated_key_reported_with_hint(tmp_path: Path) -> None:
    legacy_key = "cave" + "man_intensity"
    _write(
        tmp_path,
        f"version: 2\nproject:\n  name: demo\ncontext:\n  compression:\n    {legacy_key}: full\n",
    )
    payload = explain(tmp_path, env={}, global_config={})
    assert payload["deprecated_keys"], "legacy compression key must be reported"
    entry = payload["deprecated_keys"][0]
    assert entry["key"].endswith(legacy_key)
    assert entry["replacement"] == "context.compression.terse_intensity"
    assert entry["hint"]
    assert payload["validation"]["status"] == "warning"


# ── CFG-006: invalid config fails with a useful error ────────────────────────


def test_unparseable_yaml_raises_configuration_error(tmp_path: Path) -> None:
    _write(tmp_path, "version: [unclosed\n  broken")
    with pytest.raises(ConfigurationError):
        explain(tmp_path, env={}, global_config={})
