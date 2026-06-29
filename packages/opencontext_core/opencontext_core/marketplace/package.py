"""Marketplace package bundle build / unpack / manifest hash (PR-016).

A package bundle is a directory (or a ``.tar.gz`` archive of one) carrying the
``marketplace.json`` manifest, an optional ``SIGNATURE.json``, and the multi-asset
``provides`` files. :func:`package_manifest_hash` is the stable digest the signer
covers — it mirrors ``workflow_packs.signing.workflow_pack_manifest_hash`` (sorted
``rglob``, per-file sha256, excludes the signature file) so the signing precedent
is reused, not duplicated.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

from opencontext_core.marketplace.manifest import (
    PACKAGE_MANIFEST_NAME,
    MarketplacePackage,
)

SIGNATURE_NAME = "SIGNATURE.json"


def package_manifest_hash(pkg_root: Path | str) -> str:
    """Stable sha256 over a package's files (paths + contents), excluding the signature.

    Identical construction to ``workflow_pack_manifest_hash`` so signatures are
    comparable across the two facilities.
    """
    root = Path(pkg_root)
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == SIGNATURE_NAME:
            continue
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    blob = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_manifest(pkg_root: Path | str) -> MarketplacePackage:
    """Load and validate the ``marketplace.json`` manifest from a package directory."""
    manifest_path = Path(pkg_root) / PACKAGE_MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"No {PACKAGE_MANIFEST_NAME} in {pkg_root}")
    return MarketplacePackage.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def stage_package(src_dir: Path | str) -> Path:
    """Copy a package source tree into a fresh temp staging dir; return its path.

    The caller owns cleanup. Staging lets publish sign/scan without mutating the
    user's source tree.
    """
    src = Path(src_dir)
    staging = Path(tempfile.mkdtemp(prefix="oc-pkg-")) / src.name
    shutil.copytree(src, staging)
    return staging


def build_package(pkg_root: Path | str, out_path: Path | str) -> Path:
    """Archive a package directory into a ``.tar.gz`` at *out_path*.

    The archive's members are stored relative to the package root so unpacking
    reproduces the bundle layout (manifest + signature + provides assets).
    """
    root = Path(pkg_root)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                tf.add(path, arcname=path.relative_to(root).as_posix())
    return out


def unpack_package(archive_or_dir: Path | str, dest_dir: Path | str) -> Path:
    """Unpack a package archive (or copy a package dir) into *dest_dir*; return it.

    Accepts a ``.tar.gz`` archive or an already-extracted directory so the
    installer handles both a published archive and a local build dir.
    """
    source = Path(archive_or_dir)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        for path in sorted(source.rglob("*")):
            if path.is_file():
                rel = path.relative_to(source)
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
        return dest
    if tarfile.is_tarfile(source):
        with tarfile.open(source, "r:*") as tf:
            _safe_extract(tf, dest)
        return dest
    raise ValueError(f"Unsupported package source: {source}")


def _safe_extract(tf: tarfile.TarFile, dest: Path) -> None:
    """Extract a tar archive, refusing path-traversal members (zip-slip guard)."""
    dest_resolved = dest.resolve()
    for member in tf.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest_resolved)):
            raise ValueError(f"Refusing unsafe archive member: {member.name}")
    # ``filter="data"`` is the safe extraction policy (Python 3.12+); members are
    # also validated above as a path-traversal guard.
    tf.extractall(dest, filter="data")
