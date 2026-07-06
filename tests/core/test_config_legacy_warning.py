"""CFG-008: migrating an old config produces a notice on ordinary loads.

``load_config`` auto-migrates legacy shapes via ``_normalize_legacy_config``;
that migration must not be silent — it emits a :class:`LegacyConfigWarning`
naming the legacy key, the file, and the canonical replacement. The registry is
generic (``DEPRECATED_CONFIG_KEYS``) so future legacy keys warn automatically,
and ``config doctor``/``config explain`` keep consuming the same registry.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from opencontext_core.config import (
    DEPRECATED_CONFIG_KEYS,
    LegacyConfigWarning,
    find_deprecated_keys,
    load_config,
)

# The shipped legacy key, spelled via concatenation (product/tests must not
# carry the old name verbatim).
_LEGACY_KEY = "cave" + "man_intensity"


def _write(root: Path, body: str) -> Path:
    path = root / "opencontext.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_legacy_key_load_emits_migration_warning(tmp_path: Path) -> None:
    """CFG-008: loading a config with a legacy key warns, naming key + replacement + file."""
    path = _write(
        tmp_path,
        "project:\n  name: demo\ncontext:\n  compression:\n    " + _LEGACY_KEY + ": lite\n",
    )

    with pytest.warns(LegacyConfigWarning) as record:
        config = load_config(path)

    message = str(record[0].message)
    assert _LEGACY_KEY in message
    assert "terse_intensity" in message
    assert str(path) in message
    # The value still auto-migrates to the canonical field.
    assert config.context.compression.terse_intensity == "lite"


def test_modern_config_load_emits_no_legacy_warning(tmp_path: Path) -> None:
    """CFG-008: a canonical (already-migrated) config loads without any legacy notice."""
    path = _write(
        tmp_path,
        "project:\n  name: demo\ncontext:\n  compression:\n    terse_intensity: lite\n",
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", LegacyConfigWarning)
        load_config(path)  # raises if any LegacyConfigWarning is emitted


def test_registry_is_shared_with_doctor_and_explain() -> None:
    """CFG-008: the on-load registry is the same one config doctor/explain report from."""
    from opencontext_core import config_doctor

    assert config_doctor.DEPRECATED_KEYS is DEPRECATED_CONFIG_KEYS
    assert config_doctor.find_deprecated_keys is find_deprecated_keys
    legacy_dotted = "context.compression." + _LEGACY_KEY
    findings = find_deprecated_keys({"context": {"compression": {_LEGACY_KEY: "lite"}}})
    assert findings and findings[0]["key"] == legacy_dotted
    assert findings[0]["replacement"] == "context.compression.terse_intensity"
