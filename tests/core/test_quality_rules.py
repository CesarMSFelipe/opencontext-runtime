"""Behaviour tests for ``opencontext_core.quality.rules``.

Every test is tmp_path-isolated: the loader only ever reads
``tmp_path/.opencontext/quality.toml``. None of these tests touch the real
``~/.opencontext`` or the repo's own ``.opencontext`` directory.

The tests are behavioural — they assert the *meaning* of the config (defaults,
TOML key mapping, validation, the ``is_active`` gate) so they fail if the
parsing/loader logic regresses, not merely if a constant changes.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from opencontext_core.quality.rules import (
    DEFAULT_RULES,
    ArchitectureRules,
    BoundaryRule,
    LanguageRule,
    LayerRule,
    QualityConfigError,
    QualityMode,
    QualityRules,
    StandardsProfile,
    load_rules,
    parse_rules,
)


def _write_toml(root: Path, body: str) -> Path:
    """Write ``body`` to ``<root>/.opencontext/quality.toml`` and return the path."""
    cfg_dir = root / ".opencontext"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / "quality.toml"
    path.write_text(body, encoding="utf-8")
    return path


class TestDefaults:
    """The zero-config path: no file present must yield working defaults."""

    def test_missing_file_returns_default_rules(self, tmp_path: Path) -> None:
        # No .opencontext/quality.toml exists under tmp_path.
        assert not (tmp_path / ".opencontext" / "quality.toml").exists()
        rules = load_rules(tmp_path)
        assert rules is DEFAULT_RULES

    def test_default_rules_values(self) -> None:
        # These are the documented zero-config defaults the whole feature relies on.
        assert DEFAULT_RULES.enabled is True
        assert DEFAULT_RULES.max_fix_loops == 2
        assert DEFAULT_RULES.mode is QualityMode.RATCHET
        assert DEFAULT_RULES.baseline_path == ".opencontext/quality-baseline.json"
        assert DEFAULT_RULES.languages == ()
        assert isinstance(DEFAULT_RULES.architecture, ArchitectureRules)

    def test_default_architecture_values(self) -> None:
        arch = DEFAULT_RULES.architecture
        assert arch.max_cycles == 0
        assert arch.no_god_files is True
        assert arch.god_file_in_degree == 8
        assert arch.god_file_loc == 600
        assert arch.max_cc == 25
        assert arch.max_depth == 0
        assert arch.layers == ()
        assert arch.boundaries == ()

    def test_default_rules_is_active(self) -> None:
        # The feature must be live out of the box (enabled + non-off mode).
        assert DEFAULT_RULES.is_active is True

    def test_missing_file_does_not_create_anything(self, tmp_path: Path) -> None:
        load_rules(tmp_path)
        # Loader must be pure-read: it never writes a config or a directory.
        assert not (tmp_path / ".opencontext").exists()


class TestIsActive:
    """``is_active`` is the on/off gate the harness + evaluator branch on."""

    def test_off_mode_is_inactive(self) -> None:
        rules = QualityRules(mode=QualityMode.OFF)
        assert rules.is_active is False

    def test_disabled_is_inactive_even_in_strict(self) -> None:
        rules = QualityRules(enabled=False, mode=QualityMode.STRICT)
        assert rules.is_active is False

    @pytest.mark.parametrize("mode", [QualityMode.WARN, QualityMode.STRICT, QualityMode.RATCHET])
    def test_enabled_non_off_modes_are_active(self, mode: QualityMode) -> None:
        assert QualityRules(enabled=True, mode=mode).is_active is True


class TestEnums:
    """The two StrEnums must accept exactly the documented string values."""

    def test_quality_mode_values(self) -> None:
        assert {m.value for m in QualityMode} == {"off", "warn", "strict", "ratchet"}
        assert QualityMode("ratchet") is QualityMode.RATCHET

    def test_standards_profile_values(self) -> None:
        assert {p.value for p in StandardsProfile} == {"relaxed", "standard", "strict"}
        assert StandardsProfile("strict") is StandardsProfile.STRICT


class TestTopLevelLoading:
    """Top-level keys map onto the right fields with the right types."""

    def test_full_top_level(self, tmp_path: Path) -> None:
        _write_toml(
            tmp_path,
            "\n".join(
                [
                    "enabled = false",
                    "max_fix_loops = 5",
                    'mode = "strict"',
                    'baseline = "custom/path.json"',
                ]
            ),
        )
        rules = load_rules(tmp_path)
        assert rules.enabled is False
        assert rules.max_fix_loops == 5
        assert rules.mode is QualityMode.STRICT
        # The spec's top-level 'baseline' TOML key maps to baseline_path.
        assert rules.baseline_path == "custom/path.json"

    def test_partial_file_fills_defaults(self, tmp_path: Path) -> None:
        # Only set the mode; everything else must fall back to the defaults.
        _write_toml(tmp_path, 'mode = "warn"')
        rules = load_rules(tmp_path)
        assert rules.mode is QualityMode.WARN
        assert rules.enabled is True
        assert rules.max_fix_loops == DEFAULT_RULES.max_fix_loops
        assert rules.baseline_path == DEFAULT_RULES.baseline_path

    def test_mode_is_case_insensitive(self, tmp_path: Path) -> None:
        _write_toml(tmp_path, 'mode = "RATCHET"')
        assert load_rules(tmp_path).mode is QualityMode.RATCHET

    def test_unknown_top_level_keys_are_ignored(self, tmp_path: Path) -> None:
        # Forward compatibility: an unknown key must not crash the loader.
        _write_toml(tmp_path, 'mode = "warn"\nfuture_key = "value"\n')
        assert load_rules(tmp_path).mode is QualityMode.WARN

    def test_empty_file_yields_defaults(self, tmp_path: Path) -> None:
        _write_toml(tmp_path, "")
        rules = load_rules(tmp_path)
        assert rules.enabled is True
        assert rules.mode is QualityMode.RATCHET


class TestArchitectureLoading:
    """The ``[architecture]`` table and its nested arrays."""

    def test_architecture_thresholds(self, tmp_path: Path) -> None:
        _write_toml(
            tmp_path,
            "\n".join(
                [
                    "[architecture]",
                    "max_cycles = 3",
                    "no_god_files = false",
                    "god_file_in_degree = 12",
                    "god_file_loc = 400",
                    "max_cc = 30",
                    "max_depth = 7",
                ]
            ),
        )
        arch = load_rules(tmp_path).architecture
        assert arch.max_cycles == 3
        assert arch.no_god_files is False
        assert arch.god_file_in_degree == 12
        assert arch.god_file_loc == 400
        assert arch.max_cc == 30
        assert arch.max_depth == 7

    def test_architecture_partial_uses_defaults(self, tmp_path: Path) -> None:
        _write_toml(tmp_path, "[architecture]\nmax_cc = 99\n")
        arch = load_rules(tmp_path).architecture
        assert arch.max_cc == 99
        # Unset fields keep their defaults.
        assert arch.max_cycles == 0
        assert arch.no_god_files is True
        assert arch.god_file_in_degree == 8

    def test_layers_parsed(self, tmp_path: Path) -> None:
        _write_toml(
            tmp_path,
            "\n".join(
                [
                    "[[architecture.layers]]",
                    'name = "core"',
                    'paths = ["packages/*/opencontext_core/**"]',
                    "order = 0",
                    "",
                    "[[architecture.layers]]",
                    'name = "cli"',
                    'paths = ["packages/*/opencontext_cli/**", "scripts/**"]',
                    "order = 1",
                ]
            ),
        )
        layers = load_rules(tmp_path).architecture.layers
        assert len(layers) == 2
        assert all(isinstance(layer, LayerRule) for layer in layers)
        core = layers[0]
        assert core.name == "core"
        assert core.paths == ("packages/*/opencontext_core/**",)
        assert core.order == 0
        cli = layers[1]
        assert cli.paths == ("packages/*/opencontext_cli/**", "scripts/**")
        assert cli.order == 1

    def test_layer_paths_as_single_string(self, tmp_path: Path) -> None:
        # A bare string is accepted as a one-element path list for convenience.
        _write_toml(
            tmp_path,
            '[[architecture.layers]]\nname = "core"\npaths = "src/**"\n',
        )
        layers = load_rules(tmp_path).architecture.layers
        assert layers[0].paths == ("src/**",)

    def test_layer_order_defaults_to_zero(self, tmp_path: Path) -> None:
        _write_toml(
            tmp_path,
            '[[architecture.layers]]\nname = "core"\npaths = ["src/**"]\n',
        )
        assert load_rules(tmp_path).architecture.layers[0].order == 0

    def test_boundaries_parsed_with_keyword_keys(self, tmp_path: Path) -> None:
        # 'from'/'to' (Python keywords) map onto from_layer/to_layer.
        _write_toml(
            tmp_path,
            "\n".join(
                [
                    "[[architecture.boundaries]]",
                    'from = "core"',
                    'to = "cli"',
                    "allow = false",
                    'reason = "core must stay adapter-agnostic"',
                ]
            ),
        )
        boundaries = load_rules(tmp_path).architecture.boundaries
        assert len(boundaries) == 1
        rule = boundaries[0]
        assert isinstance(rule, BoundaryRule)
        assert rule.from_layer == "core"
        assert rule.to_layer == "cli"
        assert rule.allow is False
        assert rule.reason == "core must stay adapter-agnostic"

    def test_boundary_defaults(self, tmp_path: Path) -> None:
        _write_toml(
            tmp_path,
            '[[architecture.boundaries]]\nfrom = "a"\nto = "b"\n',
        )
        rule = load_rules(tmp_path).architecture.boundaries[0]
        assert rule.allow is False
        assert rule.reason == ""


class TestLanguagesLoading:
    """The ``[languages.<lang>]`` per-language profile overrides."""

    def test_languages_parsed(self, tmp_path: Path) -> None:
        _write_toml(
            tmp_path,
            "\n".join(
                [
                    "[languages.python]",
                    'profile = "strict"',
                    "",
                    "[languages.typescript]",
                    'profile = "standard"',
                    "",
                    "[languages.go]",
                    'profile = "relaxed"',
                ]
            ),
        )
        languages = load_rules(tmp_path).languages
        assert all(isinstance(rule, LanguageRule) for rule in languages)
        by_name = {rule.language: rule.profile for rule in languages}
        assert by_name == {
            "python": StandardsProfile.STRICT,
            "typescript": StandardsProfile.STANDARD,
            "go": StandardsProfile.RELAXED,
        }

    def test_languages_sorted_deterministically(self, tmp_path: Path) -> None:
        _write_toml(
            tmp_path,
            "\n".join(
                [
                    "[languages.zig]",
                    'profile = "standard"',
                    "[languages.go]",
                    'profile = "standard"',
                    "[languages.python]",
                    'profile = "standard"',
                ]
            ),
        )
        names = [rule.language for rule in load_rules(tmp_path).languages]
        assert names == sorted(names) == ["go", "python", "zig"]

    def test_language_profile_defaults_to_standard(self, tmp_path: Path) -> None:
        # A language table with no profile key defaults to STANDARD.
        _write_toml(tmp_path, "[languages.rust]\n")
        languages = load_rules(tmp_path).languages
        assert languages[0].language == "rust"
        assert languages[0].profile is StandardsProfile.STANDARD


class TestValidationErrors:
    """A present-but-malformed file must raise a clear QualityConfigError."""

    def test_invalid_toml_syntax_raises(self, tmp_path: Path) -> None:
        _write_toml(tmp_path, "this is = = not valid toml")
        with pytest.raises(QualityConfigError):
            load_rules(tmp_path)

    def test_invalid_mode_raises_with_helpful_message(self, tmp_path: Path) -> None:
        _write_toml(tmp_path, 'mode = "turbo"')
        with pytest.raises(QualityConfigError) as excinfo:
            load_rules(tmp_path)
        # The message must name the offending value and list valid modes.
        assert "turbo" in str(excinfo.value)
        assert "ratchet" in str(excinfo.value)

    def test_invalid_language_profile_raises(self, tmp_path: Path) -> None:
        _write_toml(tmp_path, '[languages.python]\nprofile = "nuclear"\n')
        with pytest.raises(QualityConfigError) as excinfo:
            load_rules(tmp_path)
        assert "nuclear" in str(excinfo.value)

    def test_enabled_must_be_bool(self, tmp_path: Path) -> None:
        _write_toml(tmp_path, 'enabled = "yes"')
        with pytest.raises(QualityConfigError):
            load_rules(tmp_path)

    def test_max_fix_loops_must_be_int_not_bool(self, tmp_path: Path) -> None:
        # bool is an int subclass; the loader must reject 'true' as max_fix_loops.
        _write_toml(tmp_path, "max_fix_loops = true")
        with pytest.raises(QualityConfigError):
            load_rules(tmp_path)

    def test_max_cc_must_be_int(self, tmp_path: Path) -> None:
        _write_toml(tmp_path, '[architecture]\nmax_cc = "lots"\n')
        with pytest.raises(QualityConfigError):
            load_rules(tmp_path)

    def test_layer_requires_name(self, tmp_path: Path) -> None:
        _write_toml(tmp_path, '[[architecture.layers]]\npaths = ["src/**"]\n')
        with pytest.raises(QualityConfigError):
            load_rules(tmp_path)

    def test_boundary_requires_from_and_to(self, tmp_path: Path) -> None:
        _write_toml(tmp_path, '[[architecture.boundaries]]\nfrom = "core"\n')
        with pytest.raises(QualityConfigError):
            load_rules(tmp_path)


class TestParseRulesDirect:
    """``parse_rules`` is the filesystem-free core used by the loader."""

    def test_parse_empty_dict_is_defaults(self) -> None:
        rules = parse_rules({})
        assert rules.enabled is True
        assert rules.mode is QualityMode.RATCHET
        assert rules.architecture.max_cc == 25

    def test_parse_round_trips_nested(self) -> None:
        rules = parse_rules(
            {
                "mode": "strict",
                "architecture": {
                    "max_cycles": 2,
                    "layers": [{"name": "core", "paths": ["src/**"]}],
                    "boundaries": [{"from": "core", "to": "cli", "allow": True}],
                },
                "languages": {"python": {"profile": "strict"}},
            }
        )
        assert rules.mode is QualityMode.STRICT
        assert rules.architecture.max_cycles == 2
        assert rules.architecture.layers[0].name == "core"
        assert rules.architecture.boundaries[0].allow is True
        assert rules.languages[0].profile is StandardsProfile.STRICT

    def test_parse_rejects_non_mapping(self) -> None:
        with pytest.raises(QualityConfigError):
            parse_rules([])  # type: ignore[arg-type]


class TestIsolation:
    """Guard: the loader must never reach outside the given root."""

    def test_only_reads_under_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # If load_rules tried to read a real home/.opencontext, pointing HOME at a
        # separate empty dir and CWD at tmp_path would not change its (default)
        # result for an empty project — proving it keys solely off the root arg.
        other_home = tmp_path / "fake_home"
        other_home.mkdir()
        monkeypatch.setenv("HOME", str(other_home))
        monkeypatch.chdir(tmp_path)

        project = tmp_path / "project"
        project.mkdir()
        _write_toml(project, 'mode = "warn"')

        # A sibling project with a different config must not bleed in.
        other_project = tmp_path / "other"
        other_project.mkdir()
        _write_toml(other_project, 'mode = "strict"')

        assert load_rules(project).mode is QualityMode.WARN
        assert load_rules(other_project).mode is QualityMode.STRICT
        # The default (no-file) directory is unaffected by either.
        assert load_rules(tmp_path).mode is QualityMode.RATCHET

    def test_frozen_dataclasses_are_immutable(self) -> None:
        rules = QualityRules()
        with pytest.raises(FrozenInstanceError):
            rules.enabled = False  # type: ignore[misc]
        arch = ArchitectureRules()
        with pytest.raises(FrozenInstanceError):
            arch.max_cc = 1  # type: ignore[misc]
