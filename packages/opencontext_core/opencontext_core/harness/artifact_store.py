"""File-backed ArtifactStore — addressable, checksum-verified artifacts (PR-002, L2).

Implements the book CRUD surface (doc 24 §6):
``write(ArtifactWriteRequest) -> ArtifactRef``, ``get``, ``list_for_run`` and
``verify_checksum``. Each artifact is stored as two files under the run's
``artifacts/`` dir: ``<artifact_id>.<ext>`` (the raw content) and
``<artifact_id>.ref.json`` (the :class:`ArtifactRef` index). Checksums reuse the
shipped :func:`opencontext_core.agentic.receipt.sha256_file` helper.

Distinct from the legacy string/SDD-content ``agents.artifact_store.ArtifactStore``
(see design Decisions): that one is incompatible with this CRUD contract.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from opencontext_core.agentic.receipt import sha256_file
from opencontext_core.models.artifact import ArtifactSource, ArtifactWriteRequest
from opencontext_core.models.run_manifest import ArtifactRef
from opencontext_core.runtime.ids import new_id

_EXT_BY_MEDIA = (
    ("json", "json"),
    ("diff", "diff"),
    ("patch", "diff"),
    ("markdown", "md"),
    ("text", "txt"),
)


def _ext_for(media_type: str) -> str:
    mt = (media_type or "").lower()
    for needle, ext in _EXT_BY_MEDIA:
        if needle in mt:
            return ext
    return "bin"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".oc-atomic.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class ArtifactStore:
    """Per-run file-backed artifact registry with checksum verification."""

    def __init__(self, run_dir: Path | str) -> None:
        self.run_dir = Path(run_dir)
        self.artifacts_dir = self.run_dir / "artifacts"

    def _ref_path(self, artifact_id: str) -> Path:
        return self.artifacts_dir / f"{artifact_id}.ref.json"

    def write(self, request: ArtifactWriteRequest) -> ArtifactRef:
        """Persist one artifact's content + ref, returning the checksummed ref."""
        artifact_id = new_id("art")
        ext = _ext_for(request.media_type)
        rel_path = f"artifacts/{artifact_id}.{ext}"
        abs_path = self.run_dir / rel_path

        content = request.content
        data = content if isinstance(content, bytes) else content.encode("utf-8")
        _atomic_write_bytes(abs_path, data)

        ref = ArtifactRef(
            artifact_id=artifact_id,
            session_id=request.session_id,
            run_id=request.run_id,
            workflow_id=request.workflow_id,
            node_id=request.node_id,
            kind=request.kind,
            path=rel_path,
            media_type=request.media_type,
            produced_by=request.produced_by,
            checksum=sha256_file(abs_path),
            source=request.source,
            required=request.required,
            cache_metadata=request.cache_metadata,
            metadata=request.metadata,
        )
        _atomic_write_bytes(
            self._ref_path(artifact_id),
            ref.model_dump_json(indent=2).encode("utf-8"),
        )
        return ref

    def register_file(
        self,
        file_path: Path | str,
        *,
        kind: str,
        run_id: str,
        session_id: str = "",
        workflow_id: str | None = None,
        node_id: str | None = None,
        media_type: str = "application/octet-stream",
        produced_by: str = "runtime",
        source: ArtifactSource = "generated",
        required: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRef:
        """Register an already-on-disk file as an artifact without copying it.

        Used for ``patches/patch-NNN.diff`` (doc 24 §10): the patch keeps its
        canonical location while the manifest still references it.
        """
        file_path = Path(file_path)
        artifact_id = new_id("art")
        try:
            rel_path = file_path.relative_to(self.run_dir).as_posix()
        except ValueError:
            rel_path = str(file_path)
        ref = ArtifactRef(
            artifact_id=artifact_id,
            session_id=session_id,
            run_id=run_id,
            workflow_id=workflow_id,
            node_id=node_id,
            kind=kind,
            path=rel_path,
            media_type=media_type,
            produced_by=produced_by,
            checksum=sha256_file(file_path),
            source=source,
            required=required,
            metadata=metadata or {},
        )
        _atomic_write_bytes(
            self._ref_path(artifact_id),
            ref.model_dump_json(indent=2).encode("utf-8"),
        )
        return ref

    def get(self, artifact_id: str) -> ArtifactRef:
        """Return the stored :class:`ArtifactRef`, or raise ``KeyError``."""
        path = self._ref_path(artifact_id)
        if not path.exists():
            raise KeyError(artifact_id)
        return ArtifactRef.model_validate_json(path.read_text(encoding="utf-8"))

    def list_for_run(self, run_id: str) -> list[ArtifactRef]:
        """Return every artifact ref registered under *run_id* (sorted by id)."""
        if not self.artifacts_dir.exists():
            return []
        refs: list[ArtifactRef] = []
        for ref_path in sorted(self.artifacts_dir.glob("*.ref.json")):
            try:
                ref = ArtifactRef.model_validate_json(ref_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if ref.run_id == run_id:
                refs.append(ref)
        return refs

    def verify_checksum(self, artifact_id: str) -> bool:
        """Return True iff the on-disk content still matches the stored checksum."""
        ref = self.get(artifact_id)
        if ref.checksum is None:
            return False
        return sha256_file(self.run_dir / ref.path) == ref.checksum
