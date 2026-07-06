"""Install manifest v2 — snapshot collector, block revert, manifest-driven purge.

Contract: INSTALL_UNINSTALL_CONTRACT.md (manifest schema, uninstall algorithm,
safety rules). Pure-logic unit tests written first (strict TDD).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.paths import read_manifest, write_manifest
from opencontext_core.paths.install_manifest import (
    MANIFEST_SCHEMA_VERSION,
    build_manifest_fields,
    detect_install_method,
    detect_markers,
    global_state_roots,
    purge_from_manifest,
    snapshot_workspace,
    strip_managed_blocks,
    verify_from_manifest,
)

# ---------------------------------------------------------------------------
# detect_markers / strip_managed_blocks
# ---------------------------------------------------------------------------


def test_detect_markers_hash_form() -> None:
    text = "node_modules/\n# opencontext:storage:start\n.opencontext/\n# opencontext:storage:end\n"
    assert detect_markers(text) == ["storage"]


def test_detect_markers_html_form() -> None:
    text = "# My agents\n<!-- opencontext:stack:start -->\nrules\n<!-- opencontext:stack:end -->\n"
    assert detect_markers(text) == ["stack"]


def test_detect_markers_none() -> None:
    assert detect_markers("just a plain file\n") == []


def test_strip_managed_blocks_preserves_user_lines() -> None:
    text = (
        "node_modules/\n"
        "# opencontext:storage:start\n"
        ".storage/\n.opencontext/\n"
        "# opencontext:storage:end\n"
        "dist/\n"
    )
    stripped = strip_managed_blocks(text, ["storage"])
    assert "opencontext:storage" not in stripped
    assert "node_modules/" in stripped
    assert "dist/" in stripped
    assert ".opencontext/" not in stripped


def test_strip_managed_blocks_html_form() -> None:
    text = "intro\n<!-- opencontext:stack:start -->\nmanaged\n<!-- opencontext:stack:end -->\n"
    stripped = strip_managed_blocks(text, ["stack"])
    assert "managed" not in stripped
    assert "intro" in stripped


def test_strip_managed_blocks_noop_without_marker() -> None:
    text = "user content only\n"
    assert strip_managed_blocks(text, ["storage"]) == text


# ---------------------------------------------------------------------------
# snapshot + collect (via build_manifest_fields)
# ---------------------------------------------------------------------------


def _fake_install(root: Path) -> None:
    """Simulate what a workspace install writes."""
    ws = root / ".opencontext"
    (ws / "policies").mkdir(parents=True)
    (ws / "policies" / "security-policy.yaml").write_text("mode: x\n", encoding="utf-8")
    (ws / "harness.yaml").write_text("workflow: sdd\n", encoding="utf-8")
    (root / "opencontext.yaml").write_text("provider: mock\n", encoding="utf-8")
    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    gitignore.write_text(
        existing + "# opencontext:storage:start\n.opencontext/\n# opencontext:storage:end\n",
        encoding="utf-8",
    )


def test_collect_records_everything_created(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    snap = snapshot_workspace(tmp_path)
    _fake_install(tmp_path)
    fields = build_manifest_fields(tmp_path, snap, agent_configs=["opencode"])

    created = fields["created_paths"]
    assert ".opencontext" in created
    assert ".opencontext/policies/security-policy.yaml" in created
    assert ".opencontext/harness.yaml" in created
    assert "opencontext.yaml" in created
    assert ".gitignore" in created  # did not exist before install
    assert "app.py" not in created  # pre-existing user file never recorded
    assert fields["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert fields["agent_configs"] == ["opencode"]
    assert fields["install_method"]
    assert fields["timestamp"]


def test_collect_marks_preexisting_gitignore_as_modified_not_created(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    snap = snapshot_workspace(tmp_path)
    _fake_install(tmp_path)
    fields = build_manifest_fields(tmp_path, snap, agent_configs=[])

    assert ".gitignore" not in fields["created_paths"]
    entries = {e["path"]: e for e in fields["modified_files"]}
    assert entries[".gitignore"]["markers"] == ["storage"]
    assert entries[".gitignore"]["created_by_install"] is False


def test_collect_marks_created_gitignore_with_marker_info(tmp_path: Path) -> None:
    snap = snapshot_workspace(tmp_path)
    _fake_install(tmp_path)
    fields = build_manifest_fields(tmp_path, snap, agent_configs=[])

    entries = {e["path"]: e for e in fields["modified_files"]}
    assert entries[".gitignore"]["markers"] == ["storage"]
    assert entries[".gitignore"]["created_by_install"] is True


def test_reinstall_merges_without_duplicates(tmp_path: Path) -> None:
    """INST-003: reinstall over an existing install must not duplicate entries."""
    snap = snapshot_workspace(tmp_path)
    _fake_install(tmp_path)
    first = build_manifest_fields(tmp_path, snap, agent_configs=["opencode"])

    snap2 = snapshot_workspace(tmp_path)  # everything already exists
    second = build_manifest_fields(tmp_path, snap2, agent_configs=["opencode"], existing=first)

    assert second["created_paths"] == first["created_paths"]
    assert len(second["created_paths"]) == len(set(second["created_paths"]))
    assert second["agent_configs"] == ["opencode"]


# ---------------------------------------------------------------------------
# write_manifest v2 roundtrip + preservation
# ---------------------------------------------------------------------------


def test_write_manifest_extra_fields_roundtrip(tmp_path: Path) -> None:
    state = tmp_path / ".opencontext"
    write_manifest(state, tmp_path, "1.7.0", extra={"schema_version": 2, "created_paths": ["a"]})
    data = read_manifest(state)
    assert data is not None
    assert data["app"] == "opencontext"  # v1 fields kept
    assert data["version"] == "1.7.0"
    assert data["schema_version"] == 2
    assert data["created_paths"] == ["a"]


def test_write_manifest_plain_rewrite_preserves_v2_fields(tmp_path: Path) -> None:
    """A later v1-style rewrite (runtime start) must not wipe install's v2 fields."""
    state = tmp_path / ".opencontext"
    write_manifest(state, tmp_path, "1.7.0", extra={"schema_version": 2, "created_paths": ["a"]})
    write_manifest(state, tmp_path, "1.7.1")  # plain ownership rewrite
    data = read_manifest(state)
    assert data is not None
    assert data["version"] == "1.7.1"
    assert data["schema_version"] == 2
    assert data["created_paths"] == ["a"]


# ---------------------------------------------------------------------------
# purge_from_manifest
# ---------------------------------------------------------------------------


def _install_and_manifest(tmp_path: Path) -> dict:
    snap = snapshot_workspace(tmp_path)
    _fake_install(tmp_path)
    return build_manifest_fields(tmp_path, snap, agent_configs=[])


def test_purge_removes_managed_and_keeps_unmanaged_sibling(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    manifest = _install_and_manifest(tmp_path)
    (tmp_path / "notes.txt").write_text("mine\n", encoding="utf-8")  # unmanaged sibling

    purge_from_manifest(tmp_path, manifest)

    assert not (tmp_path / ".opencontext").exists()
    assert not (tmp_path / "opencontext.yaml").exists()
    assert not (tmp_path / ".gitignore").exists()  # created + emptied by block revert
    assert (tmp_path / "app.py").is_file()
    assert (tmp_path / "notes.txt").is_file()


def test_purge_reverts_gitignore_block_keeping_user_lines(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    manifest = _install_and_manifest(tmp_path)

    result = purge_from_manifest(tmp_path, manifest)

    gitignore = tmp_path / ".gitignore"
    assert gitignore.is_file()  # pre-existing file is never deleted
    text = gitignore.read_text(encoding="utf-8")
    assert "node_modules/" in text
    assert "opencontext" not in text
    assert ".gitignore" in result["reverted"]


def test_purge_reports_unmanaged_leftovers_without_deleting(tmp_path: Path) -> None:
    manifest = _install_and_manifest(tmp_path)
    # Simulate a user file inside a managed (non-state) created dir.
    claude = tmp_path / ".claude" / "commands"
    claude.mkdir(parents=True)
    (claude / "oc-review.md").write_text("managed\n", encoding="utf-8")
    manifest["created_paths"] = [
        *manifest["created_paths"],
        ".claude",
        ".claude/commands",
        ".claude/commands/oc-review.md",
    ]
    (claude / "my-own.md").write_text("user\n", encoding="utf-8")

    result = purge_from_manifest(tmp_path, manifest)

    assert not (claude / "oc-review.md").exists()
    assert (claude / "my-own.md").is_file()  # unmanaged: reported, never deleted
    assert any("my-own.md" in p for p in result["unmanaged"])


def test_purge_never_follows_symlinks_out(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep\n", encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    manifest = _install_and_manifest(root)
    link = root / ".opencontext" / "link-out"
    link.symlink_to(outside)

    purge_from_manifest(root, manifest)

    assert (outside / "precious.txt").is_file()
    assert not (root / ".opencontext").exists()


def test_purge_ignores_escaping_manifest_entries(tmp_path: Path) -> None:
    """A corrupted manifest must never delete outside the project root."""
    outside = tmp_path / "outside.txt"
    outside.write_text("keep\n", encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    manifest = _install_and_manifest(root)
    manifest["created_paths"] = [*manifest["created_paths"], "../outside.txt", str(outside)]

    purge_from_manifest(root, manifest)

    assert outside.is_file()


# ---------------------------------------------------------------------------
# verify_from_manifest
# ---------------------------------------------------------------------------


def test_verify_clean_after_purge(tmp_path: Path) -> None:
    manifest = _install_and_manifest(tmp_path)
    purge_from_manifest(tmp_path, manifest)

    report = verify_from_manifest(tmp_path, manifest)
    assert report["residue"] == []
    assert report["unmanaged"] == []


def test_verify_reports_managed_residue(tmp_path: Path) -> None:
    manifest = _install_and_manifest(tmp_path)
    purge_from_manifest(tmp_path, manifest)
    (tmp_path / "opencontext.yaml").write_text("provider: mock\n", encoding="utf-8")

    report = verify_from_manifest(tmp_path, manifest)
    assert "opencontext.yaml" in report["residue"]


def test_verify_reports_unmanaged_leftovers_as_non_residue(tmp_path: Path) -> None:
    manifest = _install_and_manifest(tmp_path)
    manifest["created_paths"] = [*manifest["created_paths"], ".claude", ".claude/commands"]
    claude = tmp_path / ".claude" / "commands"
    claude.mkdir(parents=True)
    (claude / "my-own.md").write_text("user\n", encoding="utf-8")

    purge_from_manifest(tmp_path, manifest)
    report = verify_from_manifest(tmp_path, manifest)

    assert report["residue"] == []
    assert any("my-own.md" in p for p in report["unmanaged"])


def test_verify_detects_marker_residue(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    manifest = _install_and_manifest(tmp_path)
    # No purge: the managed block is still present.
    report = verify_from_manifest(tmp_path, manifest)
    assert ".gitignore" in report["residue"]


# ---------------------------------------------------------------------------
# detect_install_method / global_state_roots
# ---------------------------------------------------------------------------


def test_detect_install_method_is_known_value() -> None:
    assert detect_install_method() in {"pipx", "pip", "venv", "editable", "unknown"}


def test_global_state_roots_respect_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / "st"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / "ca"))

    roots = global_state_roots()
    as_str = [str(r) for r in roots]
    assert str(home / "cfg" / "opencontext") in as_str
    assert str(home / ".opencontext") in as_str
    assert str(home / "st" / "opencontext") in as_str
    assert str(home / "ca" / "opencontext") in as_str


def test_manifest_fields_json_serializable(tmp_path: Path) -> None:
    manifest = _install_and_manifest(tmp_path)
    json.dumps(manifest)  # must not raise


# ---------------------------------------------------------------------------
# Product (HOME) manifest — INST-001 / INST-MANIFEST-FIELDS
# ---------------------------------------------------------------------------


def _fake_product_install(home: Path) -> None:
    """Simulate what install.sh creates at HOME level."""
    venv_bin = home / ".opencontext" / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "opencontext").write_text("#!/bin/sh\n", encoding="utf-8")
    (home / ".config" / "opencontext").mkdir(parents=True)
    (home / ".bashrc").write_text(
        f"alias ll='ls -la'\n\n# OpenContext Runtime\nexport PATH=\"{venv_bin}:$PATH\"\n",
        encoding="utf-8",
    )
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "opencontext").symlink_to(venv_bin / "opencontext")


def _isolate_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))


def test_product_manifest_records_all_contract_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INST-MANIFEST-FIELDS: the product manifest records schema_version, install_id,
    install_method, product_version, created_paths, modified_files,
    shell_profile_blocks, symlinks, env_vars, agent_configs, state_paths."""
    from opencontext_core.paths.install_manifest import build_product_manifest_fields

    home = tmp_path / "home"
    _isolate_home(monkeypatch, home)
    _fake_product_install(home)

    fields = build_product_manifest_fields(home)

    assert fields["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert fields["install_id"]
    assert fields["install_method"]
    assert fields["product_version"]
    assert str(home / ".opencontext" / "venv") in fields["created_paths"]
    assert fields["modified_files"] == []
    blocks = {entry["path"] for entry in fields["shell_profile_blocks"]}
    assert str(home / ".bashrc") in blocks
    assert all(e["marker"] == "# OpenContext Runtime" for e in fields["shell_profile_blocks"])
    links = {entry["path"] for entry in fields["symlinks"]}
    assert str(home / ".local" / "bin" / "opencontext") in links
    assert fields["env_vars"] == []
    assert fields["agent_configs"] == []
    state = set(fields["state_paths"])
    assert str(home / ".opencontext") in state
    assert str(home / ".config" / "opencontext") in state
    assert fields["timestamp"]
    json.dumps(fields)  # must not raise


def test_product_manifest_ignores_foreign_local_bin_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INST-MANIFEST-FIELDS: a ~/.local/bin/opencontext symlink NOT pointing into
    ~/.opencontext belongs to another tool and is never recorded as managed."""
    from opencontext_core.paths.install_manifest import build_product_manifest_fields

    home = tmp_path / "home"
    _isolate_home(monkeypatch, home)
    other = tmp_path / "elsewhere" / "opencontext"
    other.parent.mkdir(parents=True)
    other.write_text("#!/bin/sh\n", encoding="utf-8")
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "opencontext").symlink_to(other)

    fields = build_product_manifest_fields(home)

    assert fields["symlinks"] == []


def test_product_manifest_reinstall_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INST-003: a product reinstall merges with the existing manifest — the
    install_id stays stable and no entry is duplicated or dropped."""
    from opencontext_core.paths.install_manifest import build_product_manifest_fields

    home = tmp_path / "home"
    _isolate_home(monkeypatch, home)
    _fake_product_install(home)

    first = build_product_manifest_fields(home)
    second = build_product_manifest_fields(home, existing=first)

    assert second["install_id"] == first["install_id"]
    assert second["created_paths"] == first["created_paths"]
    assert len(second["created_paths"]) == len(set(second["created_paths"]))
    assert second["shell_profile_blocks"] == first["shell_profile_blocks"]
    assert second["symlinks"] == first["symlinks"]
    assert second["state_paths"] == first["state_paths"]


def test_write_product_manifest_persists_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INST-001: write_product_manifest registers the product-scope manifest at
    ~/.opencontext/oc-manifest.json and read_manifest roundtrips it."""
    from opencontext_core.paths.install_manifest import write_product_manifest

    home = tmp_path / "home"
    _isolate_home(monkeypatch, home)
    _fake_product_install(home)

    write_product_manifest()

    data = read_manifest(home / ".opencontext")
    assert data is not None
    assert data["app"] == "opencontext"  # v1 ownership fields kept
    assert data["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert data["install_id"]
    assert any(e["path"] == str(home / ".bashrc") for e in data["shell_profile_blocks"])

    before = data["install_id"]
    write_product_manifest()  # re-register: idempotent, id preserved
    again = read_manifest(home / ".opencontext")
    assert again is not None
    assert again["install_id"] == before


def test_workspace_manifest_carries_install_id_and_shell_fields(tmp_path: Path) -> None:
    """INST-MANIFEST-FIELDS: the workspace manifest also records install_id (stable
    across reinstalls) plus shell_profile_blocks/symlinks — empty for the
    workspace scope, which never writes shell blocks or symlinks."""
    snap = snapshot_workspace(tmp_path)
    _fake_install(tmp_path)
    first = build_manifest_fields(tmp_path, snap, agent_configs=[])

    assert first["install_id"]
    assert first["shell_profile_blocks"] == []
    assert first["symlinks"] == []

    snap2 = snapshot_workspace(tmp_path)
    second = build_manifest_fields(tmp_path, snap2, agent_configs=[], existing=first)
    assert second["install_id"] == first["install_id"]
