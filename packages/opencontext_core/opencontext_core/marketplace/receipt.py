"""Package receipts (PR-016, book §31 Package Receipts).

The book requires ``package-install``/``-update``/``-remove``/
``-permission-approval`` receipts referencing the package id, version, source and
manifest/content hash. Receipts are append-only JSON files written next to the
plugin install root so an install stays auditable without registry access.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC

PACKAGE_RECEIPT_SCHEMA = "opencontext.package_receipt.v1"

RECEIPT_INSTALL = "package-install"
RECEIPT_UPDATE = "package-update"
RECEIPT_REMOVE = "package-remove"
RECEIPT_PERMISSION_APPROVAL = "package-permission-approval"


class PackageReceipt(BaseModel):
    """An auditable record of one package lifecycle event."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=PACKAGE_RECEIPT_SCHEMA)
    kind: str = Field(description="Receipt kind, e.g. 'package-install'.")
    package_id: str = Field(description="Stable package id.")
    name: str = Field(default="", description="Package name.")
    version: str = Field(description="Package version.")
    source: str = Field(default="", description="Install source kind or URL.")
    trust_level: str = Field(default="", description="Recorded trust level.")
    publisher: str = Field(default="", description="Recorded publisher.")
    manifest_hash: str | None = Field(default=None, description="Manifest/content hash.")
    permissions: list[str] = Field(
        default_factory=list, description="Granted permission set (capability:value)."
    )
    signature_verified: bool = Field(
        default=False, description="Whether a publisher signature was verified."
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


def write_package_receipt(receipts_dir: Path | str, receipt: PackageReceipt) -> Path:
    """Write a receipt as an append-only JSON file; return its path."""
    directory = Path(receipts_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = receipt.created_at.strftime("%Y%m%dT%H%M%S%f")
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", receipt.package_id) or "package"
    path = directory / f"{receipt.kind}-{safe_id}-{receipt.version}-{stamp}.json"
    path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_receipts(receipts_dir: Path | str) -> list[PackageReceipt]:
    """Load all receipts from a directory (newest first). Best-effort; skips bad files."""
    directory = Path(receipts_dir)
    if not directory.exists():
        return []
    receipts: list[PackageReceipt] = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            receipts.append(PackageReceipt.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return receipts
