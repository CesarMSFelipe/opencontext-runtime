"""AICX lockfile (Workstream N) — pin the agentic context surface.

The AICX (Agentic Context surface) lockfile records hashes of the contracts a
run depends on: the structured-output schema versions, the client capability
matrix, and the knowledge-graph shape. Pinning these makes "same surface →
same lock" verifiable, so drift (a schema bump, a graph re-index, a new client)
is detectable instead of silent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _schema_default(model: type[BaseModel], field: str = "schema_version") -> str:
    """The literal default of a model's schema_version field (no instance built)."""
    default = model.model_fields[field].default
    return str(default)


class AICXLockEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    sha256: str
    detail: str = ""


class AICXLockfile(BaseModel):
    """Reproducibility lock over the agentic context surface."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.aicx_lock.v1"
    entries: list[AICXLockEntry] = Field(default_factory=list)
    lock_hash: str = Field(description="Hash over all entries — the single comparison handle.")

    def matches(self, other: AICXLockfile) -> bool:
        return self.lock_hash == other.lock_hash


def _compute_lock_hash(entries: list[AICXLockEntry]) -> str:
    # Deterministic: hash the sorted (name, sha256) pairs.
    payload = json.dumps(sorted((e.name, e.sha256) for e in entries), separators=(",", ":"))
    return _sha(payload)


def build_lockfile(root: str | Path = ".") -> AICXLockfile:
    """Capture the current agentic context surface into a lockfile.

    Fail-closed: the graph entry reflects ``compute_graph_health`` (which reports
    ``unavailable``/``empty`` rather than raising), so a missing index still
    produces a deterministic, honest lock.
    """
    from opencontext_core.configurator.capability import build_capability_matrix
    from opencontext_core.indexing.graph_health import compute_graph_health
    from opencontext_core.models.context_contract import ContextContract
    from opencontext_core.models.run_envelope import RunEnvelope

    entries: list[AICXLockEntry] = []

    # 1. Structured-output schema surface — the contracts agents consume.
    schema_versions = {
        "run_envelope": _schema_default(RunEnvelope),
        "context_contract": _schema_default(ContextContract),
        "capability_matrix": "opencontext.capability_matrix.v1",
        "graph_health": "opencontext.graph_health.v1",
        "mcp_tool_result": "opencontext.mcp_tool_result.v1",
        "run_receipt": "opencontext.run_receipt.v2",
    }
    entries.append(
        AICXLockEntry(
            name="schemas",
            sha256=_sha(json.dumps(schema_versions, sort_keys=True)),
            detail=f"{len(schema_versions)} schema versions",
        )
    )

    # 2. Client capability matrix — which clients are supported and how.
    matrix = build_capability_matrix()
    entries.append(
        AICXLockEntry(
            name="capability_matrix",
            sha256=_sha(matrix.model_dump_json()),
            detail=f"{len(matrix.clients)} clients",
        )
    )

    # 3. Knowledge-graph shape — the indexed surface a run grounds on.
    graph = compute_graph_health(Path(root) / ".storage" / "opencontext" / "context_graph.db")
    graph_sig = json.dumps(
        {
            "status": graph.status,
            "nodes": graph.nodes,
            "edges": graph.edges,
            "files": graph.files,
            "languages": graph.languages,
        },
        sort_keys=True,
    )
    entries.append(AICXLockEntry(name="graph", sha256=_sha(graph_sig), detail=graph.status))

    return AICXLockfile(entries=entries, lock_hash=_compute_lock_hash(entries))


# ── file-backed store ─────────────────────────────────────────────────────────


def _lock_path(root: str | Path) -> Path:
    return Path(root) / ".opencontext" / "aicx.lock"


def write_lockfile(root: str | Path = ".") -> Path:
    """Build and persist the lockfile to ``.opencontext/aicx.lock``."""
    lock = build_lockfile(root)
    path = _lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(lock.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_lockfile(root: str | Path = ".") -> AICXLockfile:
    """Load a persisted lockfile. Raises FileNotFoundError if absent."""
    path = _lock_path(root)
    if not path.exists():
        raise FileNotFoundError(f"AICX lockfile not found: {path}")
    return AICXLockfile.model_validate_json(path.read_text(encoding="utf-8"))


def verify_lockfile(root: str | Path = ".") -> dict[str, object]:
    """Compare the persisted lock against a freshly built one.

    Returns a structured verdict; fail-closed (``ok=False``) when no lock exists.
    """
    try:
        pinned = load_lockfile(root)
    except FileNotFoundError:
        return {"ok": False, "error": "not_locked"}
    current = build_lockfile(root)
    drifted = [e.name for e in current.entries if _sha_for(pinned, e.name) != e.sha256]
    return {
        "ok": pinned.matches(current),
        "pinned_hash": pinned.lock_hash,
        "current_hash": current.lock_hash,
        "drifted": drifted,
    }


def _sha_for(lock: AICXLockfile, name: str) -> str | None:
    return next((e.sha256 for e in lock.entries if e.name == name), None)
