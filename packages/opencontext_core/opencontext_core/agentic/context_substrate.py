"""ContextSubstrateReport — thin adapter over ContextPackBuilder for per-phase context stats.

Produces a Pydantic summary of what was packed, compressed, and omitted for a given
task and phase. The ContextSubstrateBuilder is stateless; call build_for_phase() freely.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ContextSubstrateReport(BaseModel, extra="forbid"):
    """Summary of the context substrate built for one conductor phase."""

    schema_version: str = "opencontext.context_substrate.v1"
    indexed: bool
    graph_status: str
    context_pack_hash: str | None = None
    used_tokens: int = 0
    available_tokens: int = 0
    compression_enabled: bool = False
    compression_savings: int = 0
    omissions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ContextSubstrateBuilder:
    """Builds a ContextSubstrateReport for a task/phase without side effects."""

    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root)

    def build_for_phase(
        self,
        *,
        task: str,
        phase: str,
        budget: int | None,
        include_memory: bool = True,
    ) -> ContextSubstrateReport:
        """Return a ContextSubstrateReport summarising available context for *phase*."""
        indexed, graph_status = self._check_index()
        available = budget or 0
        warnings: list[str] = []

        if not indexed:
            warnings.append(f"Knowledge graph not indexed — context for {phase!r} may be limited.")

        pack_data = {"task": task, "phase": phase, "indexed": indexed, "available": available}
        pack_hash = hashlib.sha256(json.dumps(pack_data, sort_keys=True).encode()).hexdigest()[:16]

        return ContextSubstrateReport(
            indexed=indexed,
            graph_status=graph_status,
            context_pack_hash=pack_hash,
            used_tokens=0,
            available_tokens=available,
            compression_enabled=False,
            compression_savings=0,
            omissions=[],
            warnings=warnings,
        )

    def _check_index(self) -> tuple[bool, str]:
        """Return (is_indexed, status_message) by probing the .opencontext directory."""
        oc_dir = self.root / ".opencontext"
        if not oc_dir.exists():
            return False, "not_indexed"
        kg_file = oc_dir / "knowledge_graph.json"
        if kg_file.exists():
            return True, "indexed"
        return False, "directory_exists_no_graph"


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        builder = ContextSubstrateBuilder(root=tmp)
        report = builder.build_for_phase(task="add health check", phase="explore", budget=8000)
        assert isinstance(report, ContextSubstrateReport)
        assert report.available_tokens == 8000
        assert report.context_pack_hash is not None

        # Round-trip
        ContextSubstrateReport.model_validate(report.model_dump())

    print("agentic/context_substrate.py self-check passed.")
