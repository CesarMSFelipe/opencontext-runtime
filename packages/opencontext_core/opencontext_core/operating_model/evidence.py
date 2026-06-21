"""Release evidence and prompt/context SBOM artifacts."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.models.trace import RuntimeTrace
from opencontext_core.operating_model.ai_leak import ReleaseAuditReport, ReleaseLeakScanner


class FileEvidence(BaseModel):
    """Hash-only evidence for one release file."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Release-relative path.")
    sha256: str = Field(description="SHA-256 hash.")
    size_bytes: int = Field(ge=0, description="File size.")


class ReleaseEvidence(BaseModel):
    """Release evidence artifact safe for local persistence."""

    model_config = ConfigDict(extra="forbid")

    root: str = Field(description="Audited release root.")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    files: list[FileEvidence] = Field(description="File hashes.")
    audit: ReleaseAuditReport = Field(description="Leak audit report.")
    signing_status: str = Field(default="unsigned", description="Signature status.")
    notes: list[str] = Field(default_factory=list, description="Evidence notes.")


class PromptContextSBOM(BaseModel):
    """Software-bill-of-materials style prompt/context artifact."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(description="Trace id.")
    workflow_name: str = Field(description="Workflow name.")
    prompt_hash: str = Field(description="Hash of assembled prompt sections.")
    context_pack_hash: str = Field(description="Hash of selected context metadata.")
    policy_hash: str = Field(description="Hash of policy metadata.")
    memory_refs: list[str] = Field(default_factory=list, description="Memory source refs.")
    tool_schema_hashes: list[str] = Field(
        default_factory=list,
        description="Tool schema hashes included in prompt.",
    )
    selected_sources: list[str] = Field(description="Selected source ids/paths.")
    token_estimates: dict[str, int] = Field(description="Trace token estimates.")
    raw_prompt_included: bool = Field(default=False, description="Always false by default.")


class ReleaseEvidenceBuilder:
    """Builds local release evidence without storing file contents."""

    def build(self, root: Path | str) -> ReleaseEvidence:
        """Build release evidence for a directory or file."""

        base = Path(root)
        files = [
            FileEvidence(
                path=(path.relative_to(base).as_posix() if base.is_dir() else path.name),
                sha256=_hash_bytes(path.read_bytes()),
                size_bytes=path.stat().st_size,
            )
            for path in _iter_files(base)
        ]
        return ReleaseEvidence(
            root=str(base),
            files=files,
            audit=ReleaseLeakScanner().scan(base),
            notes=[
                "No raw file contents are stored in this evidence artifact.",
                "Signing is an integrity scaffold unless a workflow-pack signature is present.",
            ],
        )


class PromptContextSBOMBuilder:
    """Builds prompt/context SBOMs from sanitized traces."""

    def build(
        self,
        trace: RuntimeTrace,
        *,
        policy_metadata: dict[str, Any] | None = None,
    ) -> PromptContextSBOM:
        """Build a prompt/context SBOM from a trace."""

        prompt_blob = "\n\n".join(section.content for section in trace.prompt_sections)
        context_blob = "\n".join(
            f"{item.id}|{item.source}|{item.tokens}|{item.classification.value}"
            for item in trace.selected_context_items
        )
        policy_blob = repr(sorted((policy_metadata or trace.metadata).items()))
        memory_refs = [
            item.source
            for item in trace.selected_context_items
            if item.source_type == "memory" or item.source.startswith("mem-")
        ]
        tool_schema_hashes = [
            _hash_text(section.content)
            for section in trace.prompt_sections
            if section.name == "tool_schemas" and section.content
        ]
        return PromptContextSBOM(
            trace_id=trace.trace_id,
            workflow_name=trace.workflow_name,
            prompt_hash=_hash_text(prompt_blob),
            context_pack_hash=_hash_text(context_blob),
            policy_hash=_hash_text(policy_blob),
            memory_refs=memory_refs,
            tool_schema_hashes=tool_schema_hashes,
            selected_sources=[item.source for item in trace.selected_context_items],
            token_estimates=trace.token_estimates,
        )


def _iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.exists():
        return []
    ignored = {".git", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache"}
    return sorted(
        path for path in root.rglob("*") if path.is_file() and not ignored.intersection(path.parts)
    )


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
