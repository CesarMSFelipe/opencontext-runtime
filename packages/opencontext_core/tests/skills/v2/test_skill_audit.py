"""Tests for skills.v2.audit — SkillAudit validates builtin Tier 0 (A6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.skills.v2.audit import AuditFinding, SkillAudit

BUILTINS_ROOT = Path(__file__).parents[3] / "opencontext_core" / "skills" / "builtins" / "core"


def test_skill_audit_validates_builtin_tier0() -> None:
    """SkillAudit.run() over the builtin/core tree produces no ERROR findings."""
    if not BUILTINS_ROOT.exists():
        pytest.skip("builtins/core not present yet")
    report = SkillAudit().run(BUILTINS_ROOT)
    errors = [f for f in report.findings if f.severity == "ERROR"]
    assert not errors, f"unexpected errors: {errors}"
    # each builtin declares the four required metadata fields
    import yaml

    for yaml_file in BUILTINS_ROOT.glob("*.yaml"):
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        for field in ("tier", "required_capabilities", "persona_compat", "contract"):
            assert field in data, f"{yaml_file.name} missing {field!r}"


def test_audit_detects_persona_skill_mismatch() -> None:
    """Audit flags a builtin that declares a persona it can't run as."""
    import tempfile

    bad = (
        "id: bad-skill\n"
        "name: bad\n"
        "tier: 0\n"
        "required_capabilities: [read]\n"
        "persona_compat: [unknown-persona]\n"
        "contract:\n"
        "  inputs: []\n"
        "  outputs: []\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "bad.yaml").write_text(bad, encoding="utf-8")
        report = SkillAudit().run(root)
    # persona mismatch should appear as a WARN or ERROR finding
    assert any(
        f.severity in ("WARN", "ERROR") and "persona" in (f.message + f.code).lower()
        for f in report.findings
    )


def test_audit_detects_confusable_skill_ids() -> None:
    """Audit flags two skills whose ids differ only in case (post-A1)."""
    import tempfile

    skill_a = (
        "id: oc-flow\nname: a\ntier: 0\nrequired_capabilities: [read]\n"
        "persona_compat: [senior-architect]\ncontract: {inputs: [], outputs: []}\n"
    )
    skill_b = (
        "id: OC-Flow\nname: b\ntier: 0\nrequired_capabilities: [read]\n"
        "persona_compat: [senior-architect]\ncontract: {inputs: [], outputs: []}\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.yaml").write_text(skill_a, encoding="utf-8")
        (root / "b.yaml").write_text(skill_b, encoding="utf-8")
        report = SkillAudit().run(root)
    assert any(
        f.severity in ("WARN", "ERROR") and "confus" in (f.message + f.code).lower()
        for f in report.findings
    )


def test_audit_finding_shape() -> None:
    """AuditFinding has severity/code/message."""
    f = AuditFinding(severity="INFO", code="ok", message="ok")
    assert f.severity == "INFO"
    assert f.code == "ok"


def test_publish_path_blocks_publish_for_skill_with_leaked_secret() -> None:
    """Audit flags a builtin that contains a likely secret in its YAML."""
    import tempfile

    bad = (
        "id: leaky\nname: leaky\ntier: 0\nrequired_capabilities: [read]\n"
        "persona_compat: [senior-architect]\n"
        "contract: {inputs: [], outputs: []}\n"
        "notes: |\n"
        "  api_key: sk-1234567890abcdef\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "leaky.yaml").write_text(bad, encoding="utf-8")
        report = SkillAudit().run(root)
    assert any(
        f.severity == "ERROR" and "secret" in (f.message + f.code).lower() for f in report.findings
    )
