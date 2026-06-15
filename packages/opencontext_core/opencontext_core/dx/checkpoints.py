"""Context checkpoint utilities.

A ``ContextCheckpoint`` is a content-derived snapshot of the inputs that shape a
context pack (project, manifest, repo-map, policy, pack, prompt). Comparing two
checkpoints yields a per-field drift report so changes are attributable to a
loadable ``trace_id``. All hashes are derived from the input text — never a
constant literal — so identical inputs always produce identical hashes and any
change is detectable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, fields


@dataclass
class ContextCheckpoint:
    """A content-derived snapshot of context state for drift comparison."""

    project_hash: str
    manifest_hash: str
    repo_map_hash: str
    policy_hash: str
    context_pack_hash: str
    prompt_hash: str
    trace_id: str = ""


@dataclass
class CheckpointDrift:
    """Per-field drift between two checkpoints."""

    changed_fields: list[str] = field(default_factory=list)
    baseline_trace_id: str = ""
    current_trace_id: str = ""

    @property
    def has_drift(self) -> bool:
        return bool(self.changed_fields)


# Hash fields compared for drift (trace_id is metadata, not a drift signal).
_HASH_FIELDS: tuple[str, ...] = (
    "project_hash",
    "manifest_hash",
    "repo_map_hash",
    "policy_hash",
    "context_pack_hash",
    "prompt_hash",
)


def fingerprint(text: str) -> str:
    """Generate a content-derived sha256 fingerprint of text."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def capture_checkpoint(
    *,
    project: str = "",
    manifest: str = "",
    repo_map: str = "",
    policy: str = "",
    context_pack: str = "",
    prompt: str = "",
    trace_id: str = "",
) -> ContextCheckpoint:
    """Capture a checkpoint with each field hash derived from its input text."""

    return ContextCheckpoint(
        project_hash=fingerprint(project),
        manifest_hash=fingerprint(manifest),
        repo_map_hash=fingerprint(repo_map),
        policy_hash=fingerprint(policy),
        context_pack_hash=fingerprint(context_pack),
        prompt_hash=fingerprint(prompt),
        trace_id=trace_id,
    )


def compare_checkpoints(
    baseline: ContextCheckpoint,
    current: ContextCheckpoint,
) -> CheckpointDrift:
    """Compare two checkpoints field-by-field and report which hashes changed."""

    baseline_names = {f.name for f in fields(baseline)}
    changed = [
        name
        for name in _HASH_FIELDS
        if name in baseline_names and getattr(baseline, name) != getattr(current, name)
    ]
    return CheckpointDrift(
        changed_fields=changed,
        baseline_trace_id=baseline.trace_id,
        current_trace_id=current.trace_id,
    )
