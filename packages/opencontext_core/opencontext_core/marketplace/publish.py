"""Marketplace publish flow (PR-016, SPEC PR-016-PUB).

``publish_package`` is the net-new publish path (no marketplace publish existed —
the only prior "publish" was the PyPI release of OpenContext itself). It:

1. loads + validates the ``marketplace.json`` manifest (schema + permissions +
   provides via Pydantic),
2. enforces semantic versioning,
3. runs the existing conservative ``SecretScanner`` as a **blocking** leak gate
   over packaged text files (fingerprint-only findings, never raw values),
4. builds the archive and signs it (publisher signature over the manifest hash).

A leaked secret aborts before any archive is produced unless explicitly
acknowledged with ``allow=True``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from opencontext_core.marketplace.manifest import MarketplacePackage
from opencontext_core.marketplace.package import (
    SIGNATURE_NAME,
    build_package,
    load_manifest,
    stage_package,
)
from opencontext_core.marketplace.signing import PackageSigner
from opencontext_core.marketplace.versioning import is_valid_semver
from opencontext_core.safety.secrets import SecretFinding, SecretScanner

# Files scanned for leaked secrets. Binary/asset extensions are skipped — the
# scanner operates on text.
_TEXT_SUFFIXES = {
    ".py", ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".cfg", ".ini",
    ".env", ".sh", ".ts", ".js", ".html", ".css", ".xml", ".rst", "",
}


@dataclass
class PublishResult:
    """Outcome of a publish attempt."""

    ok: bool
    package_id: str = ""
    version: str = ""
    archive_path: Path | None = None
    signed: bool = False
    findings: list[SecretFinding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    message: str = ""


def scan_source_for_secrets(src_dir: Path | str) -> list[SecretFinding]:
    """Scan a package source tree's text files; return fingerprint-only findings."""
    scanner = SecretScanner()
    findings: list[SecretFinding] = []
    root = Path(src_dir)
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == SIGNATURE_NAME:
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        findings.extend(scanner.scan_secret_findings(text))
    return findings


def validate_manifest(src_dir: Path | str) -> tuple[MarketplacePackage | None, list[str]]:
    """Load and validate the manifest; return ``(manifest, errors)``."""
    errors: list[str] = []
    try:
        manifest = load_manifest(src_dir)
    except FileNotFoundError as exc:
        return None, [str(exc)]
    except Exception as exc:  # schema / permission validation failure
        return None, [f"invalid manifest: {exc}"]
    if not is_valid_semver(manifest.version):
        errors.append(
            f"version '{manifest.version}' is not semantic (MAJOR.MINOR.PATCH required)"
        )
    if not manifest.id:
        errors.append("package id is required")
    return manifest, errors


def publish_package(
    src_dir: Path | str,
    *,
    key: str | None = None,
    allow: bool = False,
    out_dir: Path | str | None = None,
) -> PublishResult:
    """Build, leak-scan, validate, version, and sign a marketplace package."""
    src = Path(src_dir)
    if not src.is_dir():
        return PublishResult(ok=False, errors=[f"source is not a directory: {src}"])

    # 1-2. Validate manifest + semver before doing anything irreversible.
    manifest, errors = validate_manifest(src)
    if manifest is None or errors:
        return PublishResult(
            ok=False,
            package_id=manifest.id if manifest else "",
            version=manifest.version if manifest else "",
            errors=errors or ["manifest validation failed"],
            message="publish aborted: invalid manifest",
        )

    # 3. Blocking leak gate (before any archive is produced).
    findings = scan_source_for_secrets(src)
    if findings and not allow:
        return PublishResult(
            ok=False,
            package_id=manifest.id,
            version=manifest.version,
            findings=findings,
            errors=[f"{len(findings)} secret finding(s) — pass allow=True to acknowledge"],
            message="publish aborted: leak detected",
        )

    # 4. Build + sign in a staging copy (never mutate the user's source).
    staging = stage_package(src)
    signed = False
    try:
        if key:
            PackageSigner().write_signature(staging, key=key, publisher=manifest.publisher)
            signed = True
        out_base = Path(out_dir) if out_dir else src.parent
        archive_path = out_base / f"{manifest.id}-{manifest.version}.tar.gz"
        build_package(staging, archive_path)
    finally:
        _cleanup_staging(staging)

    return PublishResult(
        ok=True,
        package_id=manifest.id,
        version=manifest.version,
        archive_path=archive_path,
        signed=signed,
        findings=findings,
        message=f"published {manifest.id} v{manifest.version}",
    )


def _cleanup_staging(staging: Path) -> None:
    import shutil

    parent = staging.parent
    shutil.rmtree(parent, ignore_errors=True)
