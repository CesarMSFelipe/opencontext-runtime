"""Manifest-driven uninstall through handle_uninstall (GAP-022 / GAP-023).

Contract: INSTALL_UNINSTALL_CONTRACT.md — manifest-driven purge deletes exactly
created_paths + state_paths, reverts managed blocks, reports (never deletes)
unmanaged leftovers, verifies per scope, and dry-run deletes nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from opencontext_core.paths import write_manifest


def _isolate_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.delenv("OPENCONTEXT_STORAGE_MODE", raising=False)


def _seed_installed_workspace(root: Path) -> None:
    """A workspace as a v2-manifest install leaves it."""
    ws = root / ".opencontext"
    (ws / "sdd").mkdir(parents=True)
    (ws / "sdd" / "context.json").write_text("{}\n", encoding="utf-8")
    (ws / "harness.yaml").write_text("workflow: sdd\n", encoding="utf-8")
    (root / "opencontext.yaml").write_text("provider: mock\n", encoding="utf-8")
    (root / ".gitignore").write_text(
        "node_modules/\n# opencontext:storage:start\n.opencontext/\n# opencontext:storage:end\n",
        encoding="utf-8",
    )
    write_manifest(
        ws,
        root,
        "1.7.0",
        extra={
            "schema_version": 2,
            "install_method": "editable",
            "product_version": "1.7.0",
            "created_paths": [
                ".opencontext",
                ".opencontext/sdd",
                ".opencontext/sdd/context.json",
                ".opencontext/harness.yaml",
                "opencontext.yaml",
            ],
            "modified_files": [
                {"path": ".gitignore", "markers": ["storage"], "created_by_install": False}
            ],
            "agent_configs": [],
            "state_paths": [".opencontext"],
            "timestamp": "2026-07-06T00:00:00+00:00",
        },
    )
    # User content that must survive every purge.
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")


def _args(root: Path, **overrides) -> SimpleNamespace:
    base = dict(
        agents=[],
        all_agents=False,
        scope="workspace",
        yes=True,
        json=True,
        dry_run=False,
        root=str(root),
        purge=True,
        full=False,
        verify=True,
        global_state=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _run(monkeypatch, capsys, args) -> tuple[int, dict]:
    import opencontext_cli.main as main_mod
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    code = 0
    try:
        handle_uninstall(args)
    except SystemExit as exc:
        code = int(exc.code or 0)
    out = capsys.readouterr().out
    return code, json.loads(out)


@pytest.fixture()
def ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _isolate_home(monkeypatch, tmp_path / "home")
    root = tmp_path / "repo"
    root.mkdir()
    _seed_installed_workspace(root)
    # An agent config so detect_installed() finds something to deconfigure.
    claude_dir = tmp_path / "home" / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.json").write_text("{}\n", encoding="utf-8")
    return root


def test_manifest_purge_removes_managed_keeps_unmanaged(ws, monkeypatch, capsys) -> None:
    (ws / "notes.txt").write_text("mine\n", encoding="utf-8")
    code, report = _run(monkeypatch, capsys, _args(ws))

    assert code == 0
    assert report["purge_source"] == "manifest"
    assert report["verify"]["passed"] is True
    assert not (ws / ".opencontext").exists()
    assert not (ws / "opencontext.yaml").exists()
    assert (ws / "app.py").is_file()
    assert (ws / "notes.txt").is_file()


def test_manifest_purge_reverts_gitignore_block_keeps_user_lines(ws, monkeypatch, capsys) -> None:
    code, report = _run(monkeypatch, capsys, _args(ws))

    assert code == 0
    gitignore = ws / ".gitignore"
    assert gitignore.is_file()  # pre-existing (created_by_install False): never deleted
    text = gitignore.read_text(encoding="utf-8")
    assert "node_modules/" in text
    assert "opencontext" not in text
    assert ".gitignore" in report["reverted"]


def test_dry_run_plans_from_manifest_and_deletes_nothing(ws, monkeypatch, capsys) -> None:
    code, report = _run(monkeypatch, capsys, _args(ws, dry_run=True))

    assert code == 0
    assert report["dry_run"] is True
    plan = report["purge_plan"]
    assert plan["source"] == "manifest"
    assert "opencontext.yaml" in plan["created_paths"]
    assert ".opencontext" in plan["state_paths"]
    assert (ws / ".opencontext").is_dir()
    assert (ws / "opencontext.yaml").is_file()
    assert "opencontext" in (ws / ".gitignore").read_text(encoding="utf-8")


def test_verify_exit_9_when_managed_residue_remains(ws, monkeypatch, capsys) -> None:
    # Simulate a purge failure: a managed file the purge cannot see gets
    # re-created between purge and verify via a read-only trick is overkill;
    # instead verify against a manifest claiming a file that still exists.
    # Add a managed path entry pointing at a file the purge will not remove
    # (it is re-created by the test through monkeypatching the purge).
    import opencontext_cli.commands.uninstall_cmd as mod
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall  # noqa: F401

    real_purge = mod._purge_workspace_with_manifest

    def purge_then_recreate(root, manifest):
        result = real_purge(root, manifest)
        (Path(str(root)) / "opencontext.yaml").write_text("provider: mock\n", encoding="utf-8")
        return result

    monkeypatch.setattr(mod, "_purge_workspace_with_manifest", purge_then_recreate)
    code, report = _run(monkeypatch, capsys, _args(ws))

    # INSTALL_UNINSTALL_CONTRACT: managed residue after purge/verify exits 9.
    assert code == 9
    assert report["exit_code"] == 9
    assert report["verify"]["passed"] is False
    assert any("opencontext.yaml" in p for p in report["verify"]["residue"])


def test_verify_exit_0_with_only_unmanaged_leftovers(ws, monkeypatch, capsys) -> None:
    # An unmanaged file inside a managed created dir (not a state dir).
    claude = ws / ".claude" / "commands"
    claude.mkdir(parents=True)
    (claude / "my-own.md").write_text("user\n", encoding="utf-8")
    manifest_file = ws / ".opencontext" / "oc-manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest["created_paths"] = [*manifest["created_paths"], ".claude", ".claude/commands"]
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    code, report = _run(monkeypatch, capsys, _args(ws))

    assert code == 0
    assert report["verify"]["passed"] is True
    assert (claude / "my-own.md").is_file()
    assert any("my-own.md" in p for p in report["verify"]["unmanaged"])


def test_global_scope_purges_home_state_and_verifies_globally(
    ws, tmp_path, monkeypatch, capsys
) -> None:
    home = tmp_path / "home"
    (home / ".config" / "opencontext").mkdir(parents=True)
    (home / ".config" / "opencontext" / "user-config.json").write_text("{}\n", encoding="utf-8")
    (home / ".opencontext" / "backups").mkdir(parents=True)
    (home / ".local" / "state" / "opencontext" / "projects").mkdir(parents=True)
    (home / ".cache" / "opencontext").mkdir(parents=True)

    code, report = _run(monkeypatch, capsys, _args(ws, scope="global"))

    assert code == 0, report
    assert report["verify"]["passed"] is True
    assert report["verify"]["global_residue"] == []
    assert not (home / ".config" / "opencontext").exists()
    assert not (home / ".opencontext").exists()
    assert not (home / ".local" / "state" / "opencontext").exists()
    assert not (home / ".cache" / "opencontext").exists()
    # Global scope must NOT touch the workspace (verify scans only global paths).
    assert (ws / ".opencontext").is_dir()
    assert (ws / "opencontext.yaml").is_file()
    assert "opencontext" in (ws / ".gitignore").read_text(encoding="utf-8")
