"""Marketplace package signing & verification (PR-016, book §31 "official package signing").

Mirrors the ``workflow_packs.signing`` precedent: an HMAC-sha256 signature over the
package manifest hash, with a reserved ``public_key_hint`` seam for asymmetric
publisher keys (``official``/``verified``). The signature is written as
``SIGNATURE.json`` inside the bundle and recomputed on install to detect tamper.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from opencontext_core.marketplace.manifest import PackageSignature
from opencontext_core.marketplace.package import (
    SIGNATURE_NAME,
    package_manifest_hash,
)


class PackageSigner:
    """Signs a marketplace package with a local HMAC key."""

    def sign(
        self,
        pkg_root: Path | str,
        *,
        key: str,
        publisher: str = "",
        public_key_hint: str | None = None,
    ) -> PackageSignature:
        """Create a publisher signature over the package's manifest hash."""
        root = Path(pkg_root)
        manifest_hash = package_manifest_hash(root)
        signature = hmac.new(
            key.encode("utf-8"),
            manifest_hash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return PackageSignature(
            manifest_hash=manifest_hash,
            signature=signature,
            publisher=publisher,
            public_key_hint=public_key_hint,
        )

    def write_signature(
        self,
        pkg_root: Path | str,
        *,
        key: str,
        publisher: str = "",
    ) -> Path:
        """Sign and write ``SIGNATURE.json`` into the package directory."""
        root = Path(pkg_root)
        signature = self.sign(root, key=key, publisher=publisher)
        path = root / SIGNATURE_NAME
        path.write_text(signature.model_dump_json(indent=2), encoding="utf-8")
        return path


class PackageVerifier:
    """Verifies a marketplace package's publisher signature."""

    def load_signature(self, pkg_root: Path | str) -> PackageSignature | None:
        """Return the bundle's stored signature, or None when unsigned."""
        path = Path(pkg_root) / SIGNATURE_NAME
        if not path.exists():
            return None
        return PackageSignature.model_validate_json(path.read_text(encoding="utf-8"))

    def verify(self, pkg_root: Path | str, *, key: str) -> bool:
        """Return whether the bundle's signature is valid for *key*.

        Recomputes the manifest hash from disk (so any tampered file fails) and
        constant-time compares the HMAC. A missing signature returns False.
        """
        root = Path(pkg_root)
        stored = self.load_signature(root)
        if stored is None:
            return False
        expected = PackageSigner().sign(root, key=key)
        # The recomputed manifest hash must match (tamper-evident) AND the HMAC
        # must verify under the provided key.
        if not hmac.compare_digest(stored.manifest_hash, expected.manifest_hash):
            return False
        return hmac.compare_digest(stored.signature, expected.signature)
