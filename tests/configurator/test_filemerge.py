"""Safe, reversible, idempotent writes into files the user co-owns."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.configurator.filemerge import (
    inject_managed_section,
    merge_mcp_servers,
    write_text_atomic,
)


def test_inject_new_section_preserves_user_content() -> None:
    existing = "# My Project\n\nMy own notes.\n"
    out = inject_managed_section(existing, "rules", "Managed rules body.")
    assert "My own notes." in out  # user content untouched
    assert "<!-- opencontext:rules:start -->" in out
    assert "<!-- opencontext:rules:end -->" in out
    assert "Managed rules body." in out


def test_reinject_replaces_in_place_without_duplicating() -> None:
    once = inject_managed_section("user line\n", "rules", "v1")
    twice = inject_managed_section(once, "rules", "v2")
    assert twice.count("opencontext:rules:start") == 1
    assert "v2" in twice and "v1" not in twice
    assert "user line" in twice  # still preserved


def test_empty_content_removes_managed_section_only() -> None:
    seeded = inject_managed_section("keep me\n", "rules", "managed")
    removed = inject_managed_section(seeded, "rules", "")
    assert "opencontext:rules" not in removed
    assert "keep me" in removed


def test_merge_mcp_servers_keeps_existing_servers() -> None:
    existing = {"mcpServers": {"other": {"command": "x"}}, "userKey": 1}
    merged = merge_mcp_servers(existing, {"opencontext": {"command": "opencontext"}})
    assert merged["mcpServers"]["other"] == {"command": "x"}  # not dropped
    assert merged["mcpServers"]["opencontext"] == {"command": "opencontext"}
    assert merged["userKey"] == 1  # unrelated keys preserved


def test_merge_mcp_servers_custom_root_key() -> None:
    # VS Code / Copilot use the "servers" root key, not "mcpServers".
    merged = merge_mcp_servers({}, {"opencontext": {"command": "x"}}, root_key="servers")
    assert merged["servers"]["opencontext"] == {"command": "x"}


def test_write_atomic_is_idempotent_and_refuses_symlinks(tmp_path: Path) -> None:
    p = tmp_path / "f.md"
    assert write_text_atomic(p, "a") is True
    assert write_text_atomic(p, "a") is False  # byte-identical -> no write
    assert write_text_atomic(p, "b") is True

    target = tmp_path / "t.md"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "l.md"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        write_text_atomic(link, "y")
