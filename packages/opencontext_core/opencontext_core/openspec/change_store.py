"""OpenSpecChangeStore — filesystem artifact storage for SDD changes.

Stores change metadata and markdown artifacts under:
  openspec/changes/<change_id>/metadata.json
  openspec/changes/<change_id>/<artifact>.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from opencontext_core.compat import UTC


class OpenSpecChangeMetadata(BaseModel):
    """Metadata for a single SDD change stored in OpenSpec."""

    change_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    artifacts: list[str] = Field(default_factory=list)


class OpenSpecChangeStore:
    """Read/write SDD change artifacts under the openspec directory."""

    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root)

    def _change_dir(self, change_id: str) -> Path:
        return self.root / "openspec" / "changes" / change_id

    def _metadata_path(self, change_id: str) -> Path:
        return self._change_dir(change_id) / "metadata.json"

    def ensure(self, change_id: str) -> OpenSpecChangeMetadata:
        """Create the change directory and metadata.json if not present.

        Returns the existing or newly created metadata.
        """
        meta_path = self._metadata_path(change_id)
        if meta_path.exists():
            return OpenSpecChangeMetadata.model_validate_json(meta_path.read_text())
        meta = OpenSpecChangeMetadata(change_id=change_id)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta.model_dump(mode="json"), indent=2), encoding="utf-8")
        return meta

    def write_markdown(self, change_id: str, artifact: str, content: str) -> Path:
        """Write *content* to ``<artifact>.md`` under the change directory.

        Registers the artifact in metadata.json (deduped).
        """
        self.ensure(change_id)
        artifact_path = self._change_dir(change_id) / f"{artifact}.md"
        artifact_path.write_text(content, encoding="utf-8")
        self.touch(change_id, artifact=artifact)
        return artifact_path

    def read_markdown(self, change_id: str, artifact: str) -> str:
        """Return the content of ``<artifact>.md``; raises FileNotFoundError if absent."""
        artifact_path = self._change_dir(change_id) / f"{artifact}.md"
        return artifact_path.read_text(encoding="utf-8")

    def touch(self, change_id: str, *, artifact: str | None = None) -> OpenSpecChangeMetadata:
        """Bump ``updated_at`` and optionally register *artifact* in the metadata."""
        meta_path = self._metadata_path(change_id)
        if not meta_path.exists():
            return self.ensure(change_id)
        meta = OpenSpecChangeMetadata.model_validate_json(meta_path.read_text())
        new_artifacts = list(meta.artifacts)
        if artifact and artifact not in new_artifacts:
            new_artifacts.append(artifact)
        updated = meta.model_copy(
            update={
                "updated_at": datetime.now(tz=UTC),
                "artifacts": new_artifacts,
            }
        )
        meta_path.write_text(
            json.dumps(updated.model_dump(mode="json"), indent=2), encoding="utf-8"
        )
        return updated


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        store = OpenSpecChangeStore(root=tmp)

        # ensure creates the metadata.json
        meta = store.ensure("my-change")
        assert meta.change_id == "my-change"
        assert (Path(tmp) / "openspec" / "changes" / "my-change" / "metadata.json").exists()

        # write → read round-trip
        store.write_markdown("my-change", "proposal", "hello world")
        content = store.read_markdown("my-change", "proposal")
        assert content == "hello world", f"Got: {content!r}"

        # touch bumps updated_at
        meta2 = store.touch("my-change")
        assert "proposal" in meta2.artifacts

    print("openspec/change_store.py self-check passed.")
