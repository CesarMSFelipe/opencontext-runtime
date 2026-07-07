"""product / workspace / agents scope hierarchy — thin delegations.

INSTALL_UNINSTALL_CONTRACT scope mapping as top-level commands: each subcommand
builds the delegate's namespace and calls the same handler the flat command
uses (install / status / setup / uninstall / capabilities). No scope logic
lives in the hierarchy commands themselves.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from opencontext_cli.commands.scopes_cmd import (
    handle_agents,
    handle_product,
    handle_workspace,
)
from opencontext_cli.main import _build_parser


def _parse(argv: list[str]) -> argparse.Namespace:
    return _build_parser().parse_args(argv)


def _isolate_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))


# ---------------------------------------------------------------------------
# Registration + maturity
# ---------------------------------------------------------------------------


def test_hierarchy_commands_registered() -> None:
    parser = _build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    for cmd in ("product", "workspace", "agents"):
        assert cmd in sub.choices, f"'{cmd}' not registered as a top-level command"


def test_hierarchy_commands_are_preview_in_both_maturity_maps() -> None:
    from opencontext_cli.command_maturity import COMMAND_MATURITY as visibility_map
    from opencontext_cli.contracts.command_registry import COMMAND_MATURITY as contract_map

    for cmd in ("product", "workspace", "agents"):
        assert visibility_map.get(cmd) == "preview"
        assert contract_map.get(cmd) == "preview"


def test_dispatch_routes_product(monkeypatch: pytest.MonkeyPatch) -> None:
    import opencontext_cli.main as main_mod

    seen: dict = {}
    monkeypatch.setattr(main_mod, "handle_product", lambda a: seen.update(vars(a)))
    main_mod._dispatch(_parse(["product", "status", "--json"]))
    assert seen.get("product_command") == "status"


# ---------------------------------------------------------------------------
# product — the OpenContext installation itself
# ---------------------------------------------------------------------------


def test_product_status_json_reads_global_manifest_and_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _isolate_home(monkeypatch, tmp_path / "home")
    handle_product(_parse(["product", "status", "--json"]))
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "product.status.v1"
    assert out["status"] == "passed"
    assert out["version"]
    assert out["manifest_present"] is False
    assert out["manifest"] is None
    assert isinstance(out["install_methods"], list)


def test_product_status_json_surfaces_existing_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    home = tmp_path / "home"
    _isolate_home(monkeypatch, home)
    from opencontext_core.paths import write_manifest

    write_manifest(home / ".opencontext", home, "1.7.0")
    handle_product(_parse(["product", "status", "--json"]))
    out = json.loads(capsys.readouterr().out)
    assert out["manifest_present"] is True
    assert out["manifest"]["app"] == "opencontext"


def test_product_install_json_keeps_package_manager_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _isolate_home(monkeypatch, tmp_path / "home")
    handle_product(_parse(["product", "install", "--json"]))
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "product.install.v1"
    assert out["status"] == "passed"
    assert out["guidance"], "must point at the package-manager install commands"
    assert isinstance(out["install_methods"], list)


def test_product_install_registers_manifest_and_status_surfaces_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """INST-001: `product install` registers the product-scope manifest under
    ~/.opencontext and `product status` reads it back."""
    home = tmp_path / "home"
    _isolate_home(monkeypatch, home)

    handle_product(_parse(["product", "install", "--json"]))
    out = json.loads(capsys.readouterr().out)
    assert out["manifest_registered"] is True
    assert (home / ".opencontext" / "oc-manifest.json").is_file()

    handle_product(_parse(["product", "status", "--json"]))
    status = json.loads(capsys.readouterr().out)
    assert status["manifest_present"] is True
    manifest = status["manifest"]
    for key in (
        "schema_version",
        "install_id",
        "install_method",
        "product_version",
        "created_paths",
        "modified_files",
        "shell_profile_blocks",
        "symlinks",
        "env_vars",
        "agent_configs",
        "state_paths",
        "timestamp",
    ):
        assert key in manifest, f"product manifest is missing contract field '{key}'"


def test_product_uninstall_delegates_to_global_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    import opencontext_cli.commands.uninstall_cmd as uninstall_mod

    seen: dict = {}
    monkeypatch.setattr(uninstall_mod, "handle_uninstall", lambda a: seen.update(vars(a)))
    handle_product(_parse(["product", "uninstall", "--purge", "--verify", "--yes", "--json"]))
    assert seen["scope"] == "global"
    assert seen["purge"] is True
    assert seen["verify"] is True
    assert seen["yes"] is True
    assert seen["json"] is True
    assert seen["full"] is False


# ---------------------------------------------------------------------------
# workspace — per-repo state
# ---------------------------------------------------------------------------


def test_workspace_init_delegates_to_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import opencontext_cli.main as main_mod

    seen: dict = {}
    monkeypatch.setattr(main_mod, "_install", lambda a: seen.update(vars(a)))
    handle_workspace(_parse(["workspace", "init", str(tmp_path), "--yes"]))
    assert seen["root"] == str(tmp_path)
    assert seen["yes"] is True


def test_workspace_install_is_an_alias_for_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import opencontext_cli.main as main_mod

    seen: dict = {}
    monkeypatch.setattr(main_mod, "_install", lambda a: seen.update(vars(a)))
    handle_workspace(_parse(["workspace", "install", str(tmp_path), "--yes", "--json"]))
    assert seen["root"] == str(tmp_path)
    assert seen["json"] is True


def test_workspace_status_delegates_and_exits_with_contract_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import opencontext_cli.main as main_mod

    seen: dict = {}

    def fake_status(root: str, *, json_output: bool) -> int:
        seen.update(root=root, json_output=json_output)
        return 0

    monkeypatch.setattr(main_mod, "_status", fake_status)
    with pytest.raises(SystemExit) as exc:
        handle_workspace(_parse(["workspace", "status", str(tmp_path), "--json"]))
    assert exc.value.code == 0
    assert seen["root"] == str(tmp_path)
    assert seen["json_output"] is True


def test_workspace_uninstall_delegates_to_workspace_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import opencontext_cli.commands.uninstall_cmd as uninstall_mod

    seen: dict = {}
    monkeypatch.setattr(uninstall_mod, "handle_uninstall", lambda a: seen.update(vars(a)))
    handle_workspace(
        _parse(
            [
                "workspace",
                "uninstall",
                "--root",
                str(tmp_path),
                "--purge",
                "--verify",
                "--yes",
                "--json",
            ]
        )
    )
    assert seen["scope"] == "workspace"
    assert seen["root"] == str(tmp_path)
    assert seen["purge"] is True
    assert seen["verify"] is True


# ---------------------------------------------------------------------------
# agents — agent client config
# ---------------------------------------------------------------------------


def test_agents_install_delegates_to_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    import opencontext_cli.commands.setup_cmd as setup_mod

    seen: dict = {}
    monkeypatch.setattr(setup_mod, "handle_setup", lambda a: seen.update(vars(a)))
    handle_agents(_parse(["agents", "install", "claude-code", "--dry-run", "--json"]))
    assert seen["agents"] == ["claude-code"]
    assert seen["dry_run"] is True
    assert seen["json"] is True


def test_agents_status_delegates_to_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    import opencontext_cli.commands.capabilities_cmd as cap_mod

    seen: dict = {}
    monkeypatch.setattr(cap_mod, "handle_capabilities", lambda a: seen.update(vars(a)))
    handle_agents(_parse(["agents", "status", "--json"]))
    assert seen["json"] is True
    assert seen["agent_id"] is None


def test_agents_uninstall_delegates_agent_config_removal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opencontext_cli.commands.uninstall_cmd as uninstall_mod

    seen: dict = {}
    monkeypatch.setattr(uninstall_mod, "handle_uninstall", lambda a: seen.update(vars(a)))
    handle_agents(_parse(["agents", "uninstall", "claude-code", "--yes", "--json"]))
    assert seen["agents"] == ["claude-code"]
    assert seen["purge"] is False
    assert seen["full"] is False
    assert seen["yes"] is True
