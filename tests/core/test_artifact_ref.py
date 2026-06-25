"""Tests for ArtifactRef (slice 4: context economy)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.context.artifact_ref import ArtifactRef


def test_artifact_ref_round_trip() -> None:
    ref = ArtifactRef(
        key="spec/req-1",
        backend="local",
        path="openspec/spec.md",
        hash="deadbeef",
        required=True,
        full_content_required=False,
    )
    assert ref.key == "spec/req-1"
    assert ref.backend == "local"
    assert ref.path == "openspec/spec.md"
    assert ref.hash == "deadbeef"
    assert ref.required is True
    assert ref.full_content_required is False


def test_artifact_ref_validates_backend() -> None:
    with pytest.raises(ValidationError):
        ArtifactRef(
            key="k",
            backend="unknown_backend",
            path="p",
            hash="h",
            required=True,
        )


def test_artifact_ref_all_four_backends() -> None:
    for backend in ("local", "engram", "openspec", "aicx"):
        ref = ArtifactRef(key="k", backend=backend, path="p", hash="h", required=True)
        assert ref.backend == backend


def test_artifact_ref_serialization_round_trip() -> None:
    ref = ArtifactRef(key="k", backend="engram", path="p", hash="abc", required=False)
    payload = ref.model_dump()
    restored = ArtifactRef.model_validate(payload)
    assert restored == ref
