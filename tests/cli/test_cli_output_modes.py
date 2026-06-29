"""PR-013 SPEC-CLI-013-11: unified output modes (human/json/yaml/quiet/verbose)."""

from __future__ import annotations

from types import SimpleNamespace

import yaml

from opencontext_cli.output import OutputMode, emit, resolve_output_mode


def _human(d: dict) -> None:
    print(f"human:{d['x']}")


def test_json_flag_aliases_json_mode() -> None:
    assert resolve_output_mode(SimpleNamespace(json=True)) is OutputMode.json
    assert resolve_output_mode(SimpleNamespace(output="json")) is OutputMode.json


def test_default_is_human() -> None:
    assert resolve_output_mode(SimpleNamespace()) is OutputMode.human


def test_output_yaml(capsys) -> None:
    emit({"x": 1}, OutputMode.yaml, _human)
    out = capsys.readouterr().out
    assert yaml.safe_load(out) == {"x": 1}


def test_output_quiet_emits_nothing(capsys) -> None:
    emit({"x": 1}, OutputMode.quiet, _human)
    assert capsys.readouterr().out == ""


def test_output_verbose_uses_verbose_renderer(capsys) -> None:
    emit({"x": 1}, OutputMode.verbose, _human, verbose=lambda d: print(f"verbose:{d['x']}"))
    assert "verbose:1" in capsys.readouterr().out


def test_explicit_output_beats_json_flag() -> None:
    # --output yaml wins even if --json was also passed.
    assert resolve_output_mode(SimpleNamespace(json=True, output="yaml")) is OutputMode.yaml
