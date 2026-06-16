"""Doctor detects a shadowed opencontext binary (two copies on PATH)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.doctor.component_checks import ComponentDoctor


def _doctor() -> ComponentDoctor:
    return ComponentDoctor(OpenContextConfig.model_validate(default_config_data()))


def _fake_binary(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / "opencontext"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_no_binary_on_path_is_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    (check,) = _doctor().check_binary_path()
    assert check.ok is True


def test_single_binary_is_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = tmp_path / "bin"
    _fake_binary(d)
    monkeypatch.setenv("PATH", str(d))
    (check,) = _doctor().check_binary_path()
    assert check.ok is True
    assert "resolves to" in check.details


def test_two_binaries_flag_shadow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _fake_binary(a)
    _fake_binary(b)
    monkeypatch.setenv("PATH", os.pathsep.join([str(a), str(b)]))
    (check,) = _doctor().check_binary_path()
    assert check.ok is False
    assert check.status == "warning"
    assert "shadows" in check.details
    assert check.recommendation
