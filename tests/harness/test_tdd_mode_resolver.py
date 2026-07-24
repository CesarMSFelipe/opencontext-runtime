"""The ONE shared TDD-mode resolver — canonical precedence + normalization.

Both spines (SDD harness ``HarnessRunner._harness_governance`` and OC Flow
``OCFlowRunner._resolve_tdd_mode``) used to each hand-roll the env-var read,
``{strict,ask,off}`` normalization, and ``ask`` default. That duplicated logic is
extracted into ``harness.config.resolve_tdd_mode`` (+ ``normalize_tdd_mode``).

Contract (Rodaja 5 B): canonical precedence ``env > config-value > default``,
where a VALID env value wins, otherwise the (already source-resolved) config
value if valid, otherwise the ``ask`` default. Each spine keeps reading its OWN
source of truth and feeds the merged inputs in; the shared function owns the
env-vs-config merge, normalization, and default so the two spines can never
drift again. Behaviour is byte-identical to what each spine previously computed.
"""

from __future__ import annotations

from opencontext_core.harness.config import normalize_tdd_mode, resolve_tdd_mode

# --------------------------------------------------------------------------- #
# normalize_tdd_mode: only the three canonical modes survive; else the default.
# --------------------------------------------------------------------------- #


def test_normalize_keeps_valid_modes() -> None:
    for mode in ("strict", "ask", "off"):
        assert normalize_tdd_mode(mode) == mode


def test_normalize_maps_invalid_to_default() -> None:
    assert normalize_tdd_mode("nonsense") == "ask"
    assert normalize_tdd_mode(None) == "ask"
    assert normalize_tdd_mode("") == "ask"


def test_normalize_honours_explicit_default() -> None:
    assert normalize_tdd_mode("garbage", default="off") == "off"


# --------------------------------------------------------------------------- #
# resolve_tdd_mode: env > config > default (with normalization).
# --------------------------------------------------------------------------- #


def test_valid_env_wins_over_config() -> None:
    """A valid env value takes precedence over any config value."""
    assert resolve_tdd_mode(env_value="strict", config_value="off") == "strict"
    assert resolve_tdd_mode(env_value="off", config_value="strict") == "off"


def test_config_used_when_env_absent_or_invalid() -> None:
    """With no valid env value, the (normalized) config value is used."""
    assert resolve_tdd_mode(env_value=None, config_value="strict") == "strict"
    assert resolve_tdd_mode(env_value="bogus", config_value="off") == "off"


def test_default_when_neither_env_nor_config_valid() -> None:
    """Falls back to the canonical ``ask`` default."""
    assert resolve_tdd_mode(env_value=None, config_value=None) == "ask"
    assert resolve_tdd_mode(env_value="bogus", config_value="garbage") == "ask"


def test_invalid_env_does_not_win_over_valid_config() -> None:
    """An unrecognised env value is ignored, letting a valid config value stand."""
    assert resolve_tdd_mode(env_value="loose", config_value="strict") == "strict"
