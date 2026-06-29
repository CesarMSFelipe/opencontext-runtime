"""Marketplace install-side enforcement (PR-016, book §31 Installation Flow).

``MarketplaceInstaller`` runs a multi-asset bundle through the book's pre-activation
gates — compatibility → signature → trust → permissions → receipt — reusing the
existing distribution spine (``PluginRegistry`` placement, ``stamp_plugin_integrity``,
``_track_plugin_in_state``) and the PR-015 compatibility evaluator. It is the
*marketplace* install path; the legacy single-asset ``plugin.json`` path in
``plugin_system`` is untouched, so a revert (or ``marketplace_enabled=False``)
keeps the current behaviour.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from opencontext_core.marketplace.manifest import MarketplacePackage
from opencontext_core.marketplace.package import (
    load_manifest,
    package_manifest_hash,
    unpack_package,
)
from opencontext_core.marketplace.receipt import (
    RECEIPT_INSTALL,
    RECEIPT_REMOVE,
    PackageReceipt,
    write_package_receipt,
)
from opencontext_core.marketplace.signing import PackageVerifier
from opencontext_core.marketplace.trust import (
    TrustPolicy,
    is_trust_allowed,
    requires_signature,
)
from opencontext_core.marketplace.versioning import is_compatible
from opencontext_core.plugin_system import (
    PluginRegistry,
    _track_plugin_in_state,
    stamp_plugin_integrity,
)
from opencontext_core.plugins.compatibility import runtime_version


@dataclass
class MarketplaceInstallResult:
    """Outcome of a marketplace package install."""

    package_id: str
    version: str
    status: str  # installed | failed | refused
    message: str = ""
    trust_level: str = ""
    signature_verified: bool = False
    receipt_path: Path | None = None
    contributions: list[tuple[str, list[str]]] = field(default_factory=list)


class MarketplaceInstaller:
    """Installs marketplace bundles with full pre-activation enforcement."""

    def __init__(
        self,
        registry: PluginRegistry | None = None,
        *,
        trust_policy: TrustPolicy | None = None,
        core_version: str | None = None,
    ) -> None:
        self.registry = registry or PluginRegistry()
        self.trust_policy = trust_policy
        self.core_version = core_version or runtime_version()

    @property
    def receipts_dir(self) -> Path:
        """Auditable receipt store next to the plugin install root."""
        return self.registry.plugins_dir.parent / "receipts"

    def install(
        self,
        source: Path | str,
        *,
        verify_key: str | None = None,
    ) -> MarketplaceInstallResult:
        """Install a marketplace bundle (archive or directory) with enforcement."""
        tmp_root = Path(tempfile.mkdtemp(prefix="oc-install-"))
        unpacked = tmp_root / "pkg"
        try:
            unpack_package(source, unpacked)
            try:
                manifest = load_manifest(unpacked)
            except Exception as exc:
                return MarketplaceInstallResult(
                    package_id="",
                    version="",
                    status="failed",
                    message=f"invalid package manifest: {exc}",
                )

            # 1. Compatibility — refuse a declared-and-incompatible package.
            ok, reason = is_compatible(manifest.requires.opencontext, self.core_version)
            if not ok:
                return MarketplaceInstallResult(
                    package_id=manifest.id,
                    version=manifest.version,
                    status="refused",
                    message=f"incompatible: {reason}",
                    trust_level=str(manifest.trust_level),
                )

            # 2. Signature — required for official/verified; any present-but-invalid
            #    signature is refused regardless of trust level (tamper-evident).
            sig_verified = False
            verifier = PackageVerifier()
            stored_sig = verifier.load_signature(unpacked)
            needs_sig = requires_signature(manifest.trust_level)
            if stored_sig is not None or needs_sig:
                if verify_key is None or not verifier.verify(unpacked, key=verify_key):
                    if needs_sig or stored_sig is not None:
                        return MarketplaceInstallResult(
                            package_id=manifest.id,
                            version=manifest.version,
                            status="refused",
                            message=(
                                "signature verification failed"
                                if stored_sig is not None
                                else f"{manifest.trust_level} trust requires a valid signature"
                            ),
                            trust_level=str(manifest.trust_level),
                        )
                else:
                    sig_verified = True

            # 3. Trust gate — Runtime Policy may forbid a trust level.
            if not is_trust_allowed(manifest.trust_level, self.trust_policy):
                return MarketplaceInstallResult(
                    package_id=manifest.id,
                    version=manifest.version,
                    status="refused",
                    message=f"trust level '{manifest.trust_level}' blocked by policy",
                    trust_level=str(manifest.trust_level),
                )

            # 4. Unpack provides assets into the install root; record provenance.
            manifest_hash = package_manifest_hash(unpacked)
            self._place_bundle(unpacked, manifest, manifest_hash)

            # 5. Emit an auditable package-install receipt with the granted perms.
            receipt = PackageReceipt(
                kind=RECEIPT_INSTALL,
                package_id=manifest.id,
                name=manifest.name,
                version=manifest.version,
                source=str(source),
                trust_level=str(manifest.trust_level),
                publisher=manifest.publisher,
                manifest_hash=manifest_hash,
                permissions=manifest.granted_permissions(),
                signature_verified=sig_verified,
            )
            receipt_path = write_package_receipt(self.receipts_dir, receipt)
            _track_plugin_in_state(manifest.name, manifest.version, "marketplace", manifest.id)

            return MarketplaceInstallResult(
                package_id=manifest.id,
                version=manifest.version,
                status="installed",
                message=f"installed {manifest.id} v{manifest.version}",
                trust_level=str(manifest.trust_level),
                signature_verified=sig_verified,
                receipt_path=receipt_path,
                contributions=manifest.provides.items(),
            )
        finally:
            import shutil

            shutil.rmtree(tmp_root, ignore_errors=True)

    def remove(self, name: str, *, package_id: str = "", version: str = "") -> bool:
        """Remove an installed marketplace package and emit a remove receipt."""
        removed = self.registry.remove(name)
        if removed:
            write_package_receipt(
                self.receipts_dir,
                PackageReceipt(
                    kind=RECEIPT_REMOVE,
                    package_id=package_id or name,
                    name=name,
                    version=version,
                    source="marketplace",
                ),
            )
        return removed

    def _place_bundle(
        self,
        unpacked: Path,
        manifest: MarketplacePackage,
        manifest_hash: str,
    ) -> Path:
        """Copy bundle files into the install root and write a marketplace plugin.json.

        The install root reuses the plugin registry directory so the package is
        discoverable; the on-disk manifest carries marketplace metadata
        (schema/trust/publisher/provides) for ``info`` to surface.
        """
        install_dir = self.registry.plugins_dir / manifest.name
        if install_dir.exists():
            import shutil

            shutil.rmtree(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(unpacked.rglob("*")):
            if path.is_file():
                rel = path.relative_to(unpacked)
                target = install_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())

        now = datetime.now().isoformat()
        plugin_json = install_dir / "plugin.json"
        on_disk = {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.publisher,
            "entry_point": "plugin.py",
            "enabled": True,
            "install_source": "marketplace",
            "source_url": manifest.id,
            "installed_at": now,
            "updated_at": now,
            "permissions": manifest.permissions.model_dump(),
            # Marketplace metadata surfaced by `plugin info`.
            "schema_version": manifest.schema_version,
            "package_id": manifest.id,
            "publisher": manifest.publisher,
            "trust_level": str(manifest.trust_level),
            "category": str(manifest.category),
            "provides": manifest.provides.model_dump(),
            "manifest_hash": manifest_hash,
        }
        plugin_json.write_text(json.dumps(on_disk, indent=2), encoding="utf-8")
        if (install_dir / "plugin.py").exists():
            stamp_plugin_integrity(install_dir)
        return install_dir
