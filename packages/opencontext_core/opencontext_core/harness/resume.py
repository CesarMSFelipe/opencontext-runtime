"""ResumeManager — integrity-validated resume with artifact rehydration (PR-002, L2).

On resume (doc 24 §19) the manager loads the run manifest, verifies the checksums
of referenced artifacts, rehydrates the artifact refs, and **fails safely** —
raising a typed :class:`ResumeIntegrityError` with no state mutated — when a
``required`` artifact is missing or fails its checksum (RES-02).

Convergence (AR-CONV): it also rehydrates the prior run's Decision Log (a missing
log warns rather than aborts, so pre-convergence sessions still resume) and
validates the persisted profile/capability snapshot (absent warns on legacy,
corrupt fails safely).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opencontext_core.agentic.receipt import sha256_file
from opencontext_core.models.run_manifest import ArtifactRef, RunManifest

# Metadata marker an ExecutionProfile/capability snapshot artifact carries.
PROFILE_SNAPSHOT_MARKER = "profile_capability"


class ResumeIntegrityError(RuntimeError):
    """Raised when a resume cannot proceed safely (no partial state is mutated)."""


@dataclass
class ResumeValidation:
    """Outcome of a resume integrity check."""

    manifest: RunManifest
    rehydrated: list[ArtifactRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decision_log_entries: list[dict[str, Any]] = field(default_factory=list)


class ResumeManager:
    """Validate + rehydrate a durable run's evidence before it is resumed."""

    def __init__(self, run_dir: Path | str) -> None:
        self.run_dir = Path(run_dir)

    def load_manifest(self) -> RunManifest:
        """Load and parse ``manifest.json`` (typed error if absent/invalid)."""
        path = self.run_dir / "manifest.json"
        if not path.exists():
            raise ResumeIntegrityError(f"run manifest not found: {path}")
        try:
            return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError as exc:  # invalid schema / corrupt JSON
            raise ResumeIntegrityError(f"run manifest invalid: {exc}") from exc

    def _artifact_ok(self, ref: ArtifactRef) -> bool:
        content_path = self.run_dir / ref.path
        if not content_path.exists():
            return False
        if ref.checksum is None:
            return True
        return sha256_file(content_path) == ref.checksum

    def validate(self) -> ResumeValidation:
        """Verify artifact integrity and rehydrate refs, failing safely.

        A missing/corrupt ``required`` artifact raises before anything is touched;
        a non-required failure is recorded as a warning and skipped.
        """
        manifest = self.load_manifest()
        warnings: list[str] = []
        rehydrated: list[ArtifactRef] = []

        for ref in manifest.artifacts:
            if self._artifact_ok(ref):
                rehydrated.append(ref)
                continue
            if ref.required:
                raise ResumeIntegrityError(
                    f"required artifact {ref.artifact_id} ({ref.kind}) "
                    "is missing or fails its checksum"
                )
            warnings.append(
                f"artifact {ref.artifact_id} ({ref.kind}) missing or checksum mismatch — skipped"
            )

        decision_entries = self._rehydrate_decision_log(rehydrated, warnings)
        self._validate_profile_snapshot(manifest, warnings)

        return ResumeValidation(
            manifest=manifest,
            rehydrated=rehydrated,
            warnings=warnings,
            decision_log_entries=decision_entries,
        )

    # -- convergence (AR-CONV) ------------------------------------------------

    def _rehydrate_decision_log(
        self, rehydrated: list[ArtifactRef], warnings: list[str]
    ) -> list[dict[str, Any]]:
        """Rehydrate the prior Decision Log; a missing log warns, never aborts."""
        log_refs = [r for r in rehydrated if r.kind == "decision-log"]
        if not log_refs:
            warnings.append("no decision-log artifact — resuming without prior decision context")
            return []
        ref = log_refs[-1]  # already checksum-verified (it is in rehydrated)
        entries: list[dict[str, Any]] = []
        for line in (self.run_dir / ref.path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    def _validate_profile_snapshot(self, manifest: RunManifest, warnings: list[str]) -> None:
        """Validate the profile/capability snapshot; absent warns, corrupt aborts."""
        snaps = [
            r for r in manifest.artifacts if r.metadata.get("snapshot") == PROFILE_SNAPSHOT_MARKER
        ]
        if not snaps:
            warnings.append("no profile/capability snapshot — resuming without profile validation")
            return
        ref = snaps[-1]
        content_path = self.run_dir / ref.path
        if not content_path.exists():
            raise ResumeIntegrityError("profile/capability snapshot missing")
        if ref.checksum is not None and sha256_file(content_path) != ref.checksum:
            raise ResumeIntegrityError("profile/capability snapshot is corrupt")
        try:
            json.loads(content_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ResumeIntegrityError("profile/capability snapshot is unparseable") from exc


__all__ = [
    "PROFILE_SNAPSHOT_MARKER",
    "ResumeIntegrityError",
    "ResumeManager",
    "ResumeValidation",
]
