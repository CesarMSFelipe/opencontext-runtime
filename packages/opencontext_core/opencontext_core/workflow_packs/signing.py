"""Workflow pack integrity signatures."""

# DEPRECATED(2.0): dead module — no runtime caller (only its own tests). Superseded by
# marketplace.signing (which mirrors this precedent). Remove in 2.0.

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC


class WorkflowPackSignature(BaseModel):
    """Integrity signature for one workflow pack directory."""

    model_config = ConfigDict(extra="forbid")

    pack: str = Field(description="Workflow pack name.")
    algorithm: str = Field(default="hmac-sha256", description="Signature algorithm.")
    manifest_hash: str = Field(description="Hash of pack file manifest.")
    signature: str = Field(description="HMAC signature.")
    signed_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    public_key_hint: str | None = Field(
        default=None,
        description="Future public-key signing hint; HMAC is local integrity only.",
    )


class WorkflowPackSigner:
    """Signs workflow packs with a local HMAC key."""

    def sign(self, pack_root: Path | str, *, key: str) -> WorkflowPackSignature:
        """Create an integrity signature for a workflow pack."""

        root = Path(pack_root)
        manifest_hash = workflow_pack_manifest_hash(root)
        signature = hmac.new(
            key.encode("utf-8"),
            manifest_hash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return WorkflowPackSignature(
            pack=root.name,
            manifest_hash=manifest_hash,
            signature=signature,
        )

    def write_signature(
        self,
        pack_root: Path | str,
        *,
        key: str,
        output_name: str = "SIGNATURE.json",
    ) -> Path:
        """Sign and write a signature file into the pack."""

        root = Path(pack_root)
        signature = self.sign(root, key=key)
        path = root / output_name
        path.write_text(signature.model_dump_json(indent=2), encoding="utf-8")
        return path


class WorkflowPackVerifier:
    """Verifies local workflow-pack integrity signatures."""

    def verify(self, pack_root: Path | str, *, key: str) -> bool:
        """Return whether the pack signature is valid."""

        root = Path(pack_root)
        signature_path = root / "SIGNATURE.json"
        if not signature_path.exists():
            return False
        stored = WorkflowPackSignature.model_validate_json(
            signature_path.read_text(encoding="utf-8")
        )
        expected = WorkflowPackSigner().sign(root, key=key)
        return hmac.compare_digest(stored.signature, expected.signature)


def workflow_pack_manifest_hash(pack_root: Path | str) -> str:
    """Hash pack file paths and contents, excluding signature files."""

    root = Path(pack_root)
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "SIGNATURE.json":
            continue
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    blob = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
