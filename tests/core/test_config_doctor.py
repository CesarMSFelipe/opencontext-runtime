"""PR-013 SPEC-CLI-013-05: config doctor validation."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.config_doctor import validate


def _statuses(diags: list) -> dict[str, str]:
    return {d.name: d.status for d in diags}


def test_unknown_key_flagged_with_remediation(tmp_path: Path) -> None:
    (tmp_path / "opencontext.yaml").write_text(
        "version: 2\nproject:\n  name: demo\nbogus_key: 1\n", encoding="utf-8"
    )
    diags = validate(tmp_path)
    bad = next(d for d in diags if d.name == "config.unknown_key.bogus_key")
    assert bad.status == "failed"
    assert bad.recommendation


def test_bad_profile_flagged(tmp_path: Path) -> None:
    (tmp_path / "opencontext.yaml").write_text(
        "profile: nope\nproject:\n  name: demo\n", encoding="utf-8"
    )
    diags = validate(tmp_path)
    prof = next(d for d in diags if d.name == "config.profile")
    assert prof.status == "failed"
    assert "nope" in prof.message


def test_workflow_refs_reported(tmp_path: Path) -> None:
    (tmp_path / "opencontext.yaml").write_text(
        "version: 2\nproject:\n  name: demo\nsdd:\n  track: standard\n",
        encoding="utf-8",
    )
    diags = validate(tmp_path)
    statuses = _statuses(diags)
    assert statuses.get("config.refs") == "passed"


def test_deprecated_key_warned_with_migration_hint(tmp_path: Path) -> None:
    legacy_key = "cave" + "man_intensity"
    (tmp_path / "opencontext.yaml").write_text(
        f"version: 2\nproject:\n  name: demo\ncontext:\n  compression:\n    {legacy_key}: full\n",
        encoding="utf-8",
    )
    diags = validate(tmp_path)
    deprecated = [d for d in diags if d.name.startswith("config.deprecated_key.")]
    assert deprecated, "legacy compression key must surface a deprecation warning"
    assert deprecated[0].status == "warning"
    assert "terse_intensity" in (deprecated[0].recommendation or "")


def test_valid_config_passes(tmp_path: Path) -> None:
    (tmp_path / "opencontext.yaml").write_text(
        "version: 2\nprofile: balanced\nproject:\n  name: demo\n", encoding="utf-8"
    )
    diags = validate(tmp_path)
    failed = [d for d in diags if d.status in ("failed", "error")]
    assert not failed, [d.message for d in failed]
