"""Tests for ProfileSignal + DrupalProfileScanner (Workstream F)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from opencontext_core.project.profiles import ProfileSignal
from opencontext_profiles.scanners import DrupalProfileScanner

# ── ProfileSignal model ───────────────────────────────────────────────────────


def test_signal_minimal() -> None:
    s = ProfileSignal(profile="drupal", kind="hook", name="mymod_form_alter", file_path="m.module")
    assert s.line == 0
    assert s.detail == ""


def test_signal_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        ProfileSignal(profile="drupal", kind="hook", name="x", file_path="f", bogus=1)


def test_signal_round_trip() -> None:
    s = ProfileSignal(
        profile="drupal", kind="route", name="mymod.settings", file_path="m.routing.yml", line=3
    )
    assert ProfileSignal.model_validate(s.model_dump()).name == "mymod.settings"


# ── DrupalProfileScanner ──────────────────────────────────────────────────────


def _drupal_module(tmp_path: Path) -> Path:
    root = tmp_path / "mymod"
    (root / "src" / "Plugin" / "Block").mkdir(parents=True)
    (root / "config" / "install").mkdir(parents=True)

    (root / "mymod.info.yml").write_text(
        "name: My Module\ntype: module\ncore_version_requirement: ^10\n", encoding="utf-8"
    )
    (root / "mymod.module").write_text(
        "<?php\n"
        "function mymod_help($route_name) {\n  return '';\n}\n\n"
        "function mymod_theme($existing) {\n  return [];\n}\n",
        encoding="utf-8",
    )
    (root / "mymod.routing.yml").write_text(
        "mymod.settings:\n"
        "  path: '/admin/config/mymod'\n"
        "  defaults:\n"
        "    _form: '\\Drupal\\mymod\\Form\\SettingsForm'\n"
        "mymod.report:\n"
        "  path: '/admin/reports/mymod'\n",
        encoding="utf-8",
    )
    (root / "mymod.services.yml").write_text(
        "services:\n"
        "  mymod.manager:\n"
        "    class: Drupal\\mymod\\Manager\n"
        "  mymod.logger:\n"
        "    class: Drupal\\mymod\\Logger\n",
        encoding="utf-8",
    )
    (root / "mymod.permissions.yml").write_text(
        "administer mymod:\n  title: 'Administer my module'\n",
        encoding="utf-8",
    )
    (root / "src" / "Plugin" / "Block" / "MyBlock.php").write_text(
        "<?php\nnamespace Drupal\\mymod\\Plugin\\Block;\nclass MyBlock {\n}\n",
        encoding="utf-8",
    )
    return root


def _by_kind(signals: list[ProfileSignal], kind: str) -> list[ProfileSignal]:
    return [s for s in signals if s.kind == kind]


def test_scan_detects_manifest(tmp_path: Path) -> None:
    root = _drupal_module(tmp_path)
    signals = DrupalProfileScanner().scan(root)
    manifests = _by_kind(signals, "manifest")
    assert len(manifests) == 1
    assert manifests[0].name == "mymod"


def test_scan_detects_hooks(tmp_path: Path) -> None:
    root = _drupal_module(tmp_path)
    hooks = _by_kind(DrupalProfileScanner().scan(root), "hook")
    names = {h.name for h in hooks}
    assert {"mymod_help", "mymod_theme"} <= names
    assert all(h.line > 0 for h in hooks)


def test_scan_detects_routes(tmp_path: Path) -> None:
    root = _drupal_module(tmp_path)
    routes = _by_kind(DrupalProfileScanner().scan(root), "route")
    names = {r.name for r in routes}
    assert {"mymod.settings", "mymod.report"} == names


def test_scan_detects_services(tmp_path: Path) -> None:
    root = _drupal_module(tmp_path)
    services = _by_kind(DrupalProfileScanner().scan(root), "service")
    assert {s.name for s in services} == {"mymod.manager", "mymod.logger"}


def test_scan_detects_permissions(tmp_path: Path) -> None:
    root = _drupal_module(tmp_path)
    perms = _by_kind(DrupalProfileScanner().scan(root), "permission")
    assert [p.name for p in perms] == ["administer mymod"]


def test_scan_detects_plugin_class(tmp_path: Path) -> None:
    root = _drupal_module(tmp_path)
    plugins = _by_kind(DrupalProfileScanner().scan(root), "plugin")
    assert [p.name for p in plugins] == ["MyBlock"]


def test_scan_profile_label(tmp_path: Path) -> None:
    root = _drupal_module(tmp_path)
    signals = DrupalProfileScanner().scan(root)
    assert signals
    assert all(s.profile == "drupal" for s in signals)


# ── fail-soft ─────────────────────────────────────────────────────────────────


def test_scan_empty_project_returns_no_signals(tmp_path: Path) -> None:
    assert DrupalProfileScanner().scan(tmp_path) == []


def test_scan_malformed_yaml_yields_no_route_signals(tmp_path: Path) -> None:
    root = tmp_path / "mod"
    root.mkdir()
    (root / "mod.routing.yml").write_text("this: : : not valid yaml: [", encoding="utf-8")
    routes = _by_kind(DrupalProfileScanner().scan(root), "route")
    assert routes == []


def test_scan_accepts_explicit_paths(tmp_path: Path) -> None:
    root = _drupal_module(tmp_path)
    # Only feed the manifest path → only the manifest signal comes back.
    signals = DrupalProfileScanner().scan(root, paths=["mymod.info.yml"])
    assert [s.kind for s in signals] == ["manifest"]
