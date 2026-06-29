"""CLI: `version` + `*/migrate` with dry-run + backups (REL-13)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_cli(
    *args: str, cwd: Path | None = None, timeout: int = 120
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "opencontext_cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd or PROJECT_ROOT),
        timeout=timeout,
    )


def test_version_emits_aggregate_block() -> None:
    # `version` now defaults to a branded human banner; the machine-readable
    # aggregate block is emitted under --json (pure JSON to stdout).
    result = _run_cli("version", "--json")
    assert result.returncode == 0, result.stderr
    block = json.loads(result.stdout)
    for key in (
        "opencontext",
        "runtime_api",
        "workflow_schema",
        "plugin_api",
        "config_schema",
        "kg_schema",
        "memory_schema",
    ):
        assert key in block, f"missing {key} in version block"


def test_config_migrate_dry_run_writes_nothing(tmp_path: Path) -> None:
    cfg = tmp_path / "opencontext.yaml"
    cfg.write_text("version: 1\nprofile: balanced\n", encoding="utf-8")
    before = cfg.read_text(encoding="utf-8")
    result = _run_cli("config", "migrate", str(cfg), "--dry-run", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "v1 -> v2" in result.stdout
    assert cfg.read_text(encoding="utf-8") == before  # nothing written


def test_config_migrate_apply_backs_up_and_bumps(tmp_path: Path) -> None:
    cfg = tmp_path / "opencontext.yaml"
    cfg.write_text("version: 1\nprofile: balanced\n", encoding="utf-8")
    result = _run_cli("config", "migrate", str(cfg), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["applied"] is True
    assert payload["backup_path"] and Path(payload["backup_path"]).is_file()
    assert "version: 2" in cfg.read_text(encoding="utf-8")
    # The backup preserves the original v1 content.
    assert "version: 1" in Path(payload["backup_path"]).read_text(encoding="utf-8")


def test_migration_error_is_actionable(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    result = _run_cli("config", "migrate", str(missing), cwd=tmp_path)
    assert result.returncode == 1
    # Errors are diagnostics: they go to stderr so stdout stays machine-clean.
    assert "Suggested fix" in result.stderr


def test_memory_migrate_marks_stale_never_deletes(tmp_path: Path) -> None:
    """Direct unit over the migrator: deprecated records are marked, not erased."""
    from opencontext_core.migration import MemoryMigrator, run_migration

    doc = tmp_path / "memory.json"
    doc.write_text(
        json.dumps(
            {
                "schema_version": "opencontext.memory.v0",
                "records": [
                    {"id": "a", "deprecated": True},
                    {"id": "b"},
                ],
            }
        ),
        encoding="utf-8",
    )
    result = run_migration(MemoryMigrator(), doc, dry_run=False)
    assert result.applied is True
    data = json.loads(doc.read_text(encoding="utf-8"))
    assert len(data["records"]) == 2  # nothing deleted
    by_id = {r["id"]: r for r in data["records"]}
    assert by_id["a"].get("stale") is True
    assert "stale" not in by_id["b"]
