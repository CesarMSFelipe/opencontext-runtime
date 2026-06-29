"""Tests for the PR-016 marketplace: format, signing, publish, trust, install.

Real assertions over each in-scope requirement. DEFERRED requirements (hosted
public registry, ratings, Studio panels, the PR-017 pre-activation benchmark
runner) are intentionally NOT tested here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.marketplace import (
    MARKETPLACE_SCHEMA_VERSION,
    MarketplaceInstaller,
    MarketplacePackage,
    PackageSigner,
    PackageVerifier,
    ProvidesBlock,
    TrustLevel,
    TrustPolicy,
    build_package,
    is_compatible,
    is_marketplace_manifest,
    is_trust_allowed,
    is_valid_semver,
    load_manifest,
    package_manifest_hash,
    publish_package,
    unpack_package,
)
from opencontext_core.marketplace.receipt import RECEIPT_INSTALL, read_receipts
from opencontext_core.plugin_system import PluginRegistry

# ── Fixtures / builders ──────────────────────────────────────────────────────


def _write_package(
    root: Path,
    *,
    pkg_id: str = "acme.widget",
    name: str = "widget",
    version: str = "1.0.0",
    trust: TrustLevel = TrustLevel.COMMUNITY,
    requires: str = ">=1.0,<2.0",
    extra_files: dict[str, str] | None = None,
    permissions: dict | None = None,
) -> Path:
    """Create a marketplace package source directory; return its path."""
    pkg = root / name
    pkg.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": MARKETPLACE_SCHEMA_VERSION,
        "id": pkg_id,
        "name": name,
        "version": version,
        "publisher": "acme",
        "license": "Apache-2.0",
        "category": "framework-pack",
        "requires": {"opencontext": requires},
        "provides": {"skills": ["acme.review"], "personas": ["acme.lead"]},
        "permissions": permissions or {"network_hosts": ["api.acme.com"]},
        "trust_level": str(trust),
    }
    (pkg / "marketplace.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    body = "class OpenContextPlugin:\n    name='widget'\n"
    (pkg / "plugin.py").write_text(body, encoding="utf-8")
    for rel, body in (extra_files or {}).items():
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return pkg


def _registry(tmp_path: Path) -> PluginRegistry:
    return PluginRegistry(tmp_path / "plugins")


@pytest.fixture(autouse=True)
def _no_state_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep marketplace install from touching the real StateStore in $HOME."""
    monkeypatch.setattr(
        "opencontext_core.marketplace.install._track_plugin_in_state",
        lambda *a, **k: None,
    )


# ── Format (REQ PR-016-PKG: marketplace package manifest) ────────────────────


def test_marketplace_package_multi_asset_round_trip() -> None:
    pkg = MarketplacePackage(
        id="acme.widget",
        name="widget",
        version="1.0.0",
        provides=ProvidesBlock(skills=["a"], personas=["b"]),
    )
    data = pkg.model_dump()
    reloaded = MarketplacePackage.model_validate(data)
    assert reloaded.schema_version == MARKETPLACE_SCHEMA_VERSION
    assert reloaded.provides.skills == ["a"]
    assert reloaded.provides.personas == ["b"]
    assert reloaded.requires.opencontext  # requires range present
    assert reloaded.permissions is not None  # permissions block present
    assert reloaded.trust_level == TrustLevel.COMMUNITY


def test_is_marketplace_manifest_distinguishes_legacy_plugin() -> None:
    assert is_marketplace_manifest({"schema_version": MARKETPLACE_SCHEMA_VERSION})
    # A legacy plugin.json (no marketplace schema) is NOT a marketplace package.
    assert not is_marketplace_manifest({"name": "legacy", "version": "0.1.0"})
    assert not is_marketplace_manifest({"schema_version": "opencontext.plugin.v1"})


def test_granted_permissions_flattened_for_receipt() -> None:
    pkg = MarketplacePackage(
        id="acme.widget",
        name="widget",
        version="1.0.0",
        permissions={"network_hosts": ["api.acme.com"], "read_paths": ["/data"]},
    )
    granted = pkg.granted_permissions()
    assert "network_hosts:api.acme.com" in granted
    assert "read_paths:/data" in granted


# ── Package build / unpack / hash (REQ PR-016-PKG) ───────────────────────────


def test_build_unpack_round_trips_provides_assets(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src", extra_files={"skills/review.md": "do review"})
    archive = build_package(src, tmp_path / "out.tar.gz")
    assert archive.exists()

    dest = tmp_path / "unpacked"
    unpack_package(archive, dest)
    assert (dest / "marketplace.json").exists()
    assert (dest / "skills" / "review.md").read_text(encoding="utf-8") == "do review"
    manifest = load_manifest(dest)
    assert manifest.id == "acme.widget"


def test_manifest_hash_stable_and_excludes_signature(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src")
    h1 = package_manifest_hash(src)
    # Writing the signature file must not change the manifest hash.
    PackageSigner().write_signature(src, key="k")
    h2 = package_manifest_hash(src)
    assert h1 == h2
    # Changing a real file changes the hash.
    (src / "plugin.py").write_text("class OpenContextPlugin:\n    name='x'\n", encoding="utf-8")
    assert package_manifest_hash(src) != h1


# ── Signing (REQ PR-016-PKG: signing & provenance) ───────────────────────────


def test_sign_then_verify_true_and_tamper_false(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src")
    PackageSigner().write_signature(src, key="secret", publisher="acme")
    assert PackageVerifier().verify(src, key="secret") is True
    assert PackageVerifier().verify(src, key="wrong") is False
    # Tamper a file after signing -> verification fails (manifest hash changed).
    (src / "plugin.py").write_text("tampered", encoding="utf-8")
    assert PackageVerifier().verify(src, key="secret") is False


def test_unsigned_package_verifies_false(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src")
    assert PackageVerifier().verify(src, key="secret") is False


# ── Trust (REQ PR-016-TRUST / MKT-CONV trust levels) ─────────────────────────


def test_trust_policy_blocks_untrusted_and_floor() -> None:
    assert is_trust_allowed(TrustLevel.COMMUNITY, None) is True  # permissive default
    blocked = TrustPolicy(blocked_levels=[TrustLevel.UNTRUSTED])
    assert is_trust_allowed(TrustLevel.UNTRUSTED, blocked) is False
    assert is_trust_allowed(TrustLevel.COMMUNITY, blocked) is True
    floor = TrustPolicy(min_level=TrustLevel.VERIFIED)
    assert is_trust_allowed(TrustLevel.COMMUNITY, floor) is False
    assert is_trust_allowed(TrustLevel.OFFICIAL, floor) is True


# ── Compatibility (REQ PR-016-PKG: compatibility enforced) ───────────────────


def test_is_compatible_range_and_absent() -> None:
    ok, _ = is_compatible(">=1.0,<2.0", "1.5.0")
    assert ok is True
    bad, reason = is_compatible(">=2.0", "1.5.0")
    assert bad is False and "2.0" in reason
    # Absent requirement never blocks.
    assert is_compatible("", "1.5.0")[0] is True


def test_semver_validation() -> None:
    assert is_valid_semver("1.2.3")
    assert is_valid_semver("1.2.3-rc1")
    assert not is_valid_semver("1.2")
    assert not is_valid_semver("latest")


# ── Publish (REQ PR-016-PUB) ─────────────────────────────────────────────────


def test_publish_success_produces_archive_and_signature(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src")
    out = tmp_path / "dist"
    result = publish_package(src, key="secret", out_dir=out)
    assert result.ok is True
    assert result.archive_path is not None and result.archive_path.exists()
    assert result.signed is True
    # The published archive carries a valid signature.
    dest = tmp_path / "verify"
    unpack_package(result.archive_path, dest)
    assert PackageVerifier().verify(dest, key="secret") is True


def test_publish_blocks_on_leaked_secret_no_archive(tmp_path: Path) -> None:
    src = _write_package(
        tmp_path / "src",
        extra_files={"config.py": 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n'},
    )
    out = tmp_path / "dist"
    result = publish_package(src, key="secret", out_dir=out)
    assert result.ok is False
    assert result.findings  # at least one fingerprinted finding
    # Findings never carry the raw value.
    for f in result.findings:
        assert "AKIA" not in f.redacted_value
        assert f.fingerprint
    assert result.archive_path is None
    assert not out.exists() or not any(out.iterdir())


def test_publish_allow_overrides_leak(tmp_path: Path) -> None:
    src = _write_package(
        tmp_path / "src",
        extra_files={"config.py": 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n'},
    )
    result = publish_package(src, key="secret", allow=True, out_dir=tmp_path / "dist")
    assert result.ok is True
    assert result.archive_path is not None and result.archive_path.exists()


def test_publish_blocks_on_non_semver_version(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src", version="latest")
    result = publish_package(src, key="secret", out_dir=tmp_path / "dist")
    assert result.ok is False
    assert any("semantic" in e for e in result.errors)
    assert result.archive_path is None


def test_publish_blocks_on_invalid_manifest(tmp_path: Path) -> None:
    src = tmp_path / "bad"
    src.mkdir()
    (src / "marketplace.json").write_text('{"id": "x"}', encoding="utf-8")  # missing required
    result = publish_package(src, out_dir=tmp_path / "dist")
    assert result.ok is False
    assert result.errors


# ── Install enforcement (REQ PR-016-PKG/TRUST + MKT-CONV) ────────────────────


def test_install_community_emits_receipt_with_hash_and_perms(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src")
    installer = MarketplaceInstaller(_registry(tmp_path), core_version="1.5.0")
    result = installer.install(src)
    assert result.status == "installed"
    assert result.receipt_path is not None and result.receipt_path.exists()
    # Provides recorded; installed on disk and discoverable.
    assert ("skills", ["acme.review"]) in result.contributions
    assert (installer.registry.plugins_dir / "widget" / "plugin.json").exists()
    # Receipt references id/version/source/content-hash + the granted perms.
    receipts = read_receipts(installer.receipts_dir)
    assert receipts and receipts[0].kind == RECEIPT_INSTALL
    r = receipts[0]
    assert r.package_id == "acme.widget"
    assert r.version == "1.0.0"
    assert r.manifest_hash
    assert "network_hosts:api.acme.com" in r.permissions


def test_install_incompatible_refused(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src", requires=">=2.0")
    installer = MarketplaceInstaller(_registry(tmp_path), core_version="1.5.0")
    result = installer.install(src)
    assert result.status == "refused"
    assert "incompatible" in result.message


def test_install_no_requirement_not_falsely_failed(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src", requires="")
    installer = MarketplaceInstaller(_registry(tmp_path), core_version="1.5.0")
    assert installer.install(src).status == "installed"


def test_install_official_requires_valid_signature(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src", trust=TrustLevel.OFFICIAL)
    installer = MarketplaceInstaller(_registry(tmp_path), core_version="1.5.0")
    # Unsigned official package is refused.
    assert installer.install(src).status == "refused"
    # Signed + correct key installs and records signature verification.
    PackageSigner().write_signature(src, key="pub", publisher="acme")
    result = installer.install(src, verify_key="pub")
    assert result.status == "installed"
    assert result.signature_verified is True


def test_install_tampered_signature_refused(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src", trust=TrustLevel.VERIFIED)
    PackageSigner().write_signature(src, key="pub")
    # Tamper after signing.
    (src / "plugin.py").write_text("tampered", encoding="utf-8")
    installer = MarketplaceInstaller(_registry(tmp_path), core_version="1.5.0")
    assert installer.install(src, verify_key="pub").status == "refused"


def test_install_trust_policy_blocks_untrusted(tmp_path: Path) -> None:
    src = _write_package(tmp_path / "src", trust=TrustLevel.UNTRUSTED)
    installer = MarketplaceInstaller(
        _registry(tmp_path),
        core_version="1.5.0",
        trust_policy=TrustPolicy(blocked_levels=[TrustLevel.UNTRUSTED]),
    )
    result = installer.install(src)
    assert result.status == "refused"
    assert "untrusted" in result.message


def test_install_from_published_archive(tmp_path: Path) -> None:
    """End-to-end: publish then install the resulting signed archive."""
    src = _write_package(tmp_path / "src", trust=TrustLevel.VERIFIED)
    pub = publish_package(src, key="pub", out_dir=tmp_path / "dist")
    assert pub.ok and pub.archive_path is not None
    installer = MarketplaceInstaller(_registry(tmp_path), core_version="1.5.0")
    result = installer.install(pub.archive_path, verify_key="pub")
    assert result.status == "installed"
    assert result.signature_verified is True


# ── Config flag (rollback guard) ─────────────────────────────────────────────


def test_marketplace_enabled_flag_default_off_and_round_trips() -> None:
    from opencontext_core.config import (
        OpenContextConfig,
        PluginHostConfig,
        default_config_data,
    )

    assert PluginHostConfig().marketplace_enabled is False
    cfg = OpenContextConfig.model_validate(default_config_data())
    assert cfg.plugins.marketplace_enabled is False
